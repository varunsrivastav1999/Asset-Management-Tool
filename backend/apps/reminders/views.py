import csv
import datetime
import hashlib
import io
import secrets

import django_filters
from django.conf import settings
from django.core import signing
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.audit.services import AuditedViewSetMixin, record
from apps.core.exceptions import DomainError
from apps.core.files import private_storage
from apps.core.permissions import IsAdmin, IsManager
from apps.core.roles import effective_role
from apps.navigation.models import SidebarItem

from .engine import can_manage, compute_next_run, unsign_link
from .models import ChannelConfig, ContactSettings, NotificationPreference, ReminderLog, ReminderRule, ReminderTemplate
from .providers import get_sms_provider, sms_configured, smtp_configured
from .templating import SAMPLE_CONTEXT, VARIABLES, render, render_html, render_subject, sms_text

CHANNELS = ["email", "sms", "in_app"]
ATTACHMENTS = ["bill", "receipt_pdf", "export_csv", "export_xlsx", "export_pdf"]
RECIPIENT_TYPES = ["holder", "department_head", "managers", "users", "custom"]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


# --- channel settings ------------------------------------------------------------------------
class ChannelConfigSerializer(serializers.ModelSerializer):
    smtp_configured = serializers.SerializerMethodField()
    sms_configured = serializers.SerializerMethodField()
    from_email = serializers.SerializerMethodField()

    class Meta:
        model = ChannelConfig
        fields = [
            "email_enabled",
            "sms_enabled",
            "in_app_enabled",
            "sender_name",
            "sms_provider",
            "sms_sender_id",
            "daily_cap",
            "email_per_minute",
            "sms_per_minute",
            "smtp_configured",
            "sms_configured",
            "from_email",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def get_smtp_configured(self, obj) -> bool:
        return smtp_configured()

    def get_sms_configured(self, obj) -> bool:
        return sms_configured(obj.sms_provider)

    def get_from_email(self, obj) -> str:
        return settings.DEFAULT_FROM_EMAIL


class ChannelConfigView(APIView):
    """Global channel settings — admins only. Secrets are env-only and never returned."""

    permission_classes = [IsAdmin]

    @extend_schema(responses=ChannelConfigSerializer)
    def get(self, request):
        return Response(ChannelConfigSerializer(ChannelConfig.load()).data)

    @extend_schema(request=ChannelConfigSerializer, responses=ChannelConfigSerializer)
    def put(self, request):
        config = ChannelConfig.load()
        s = ChannelConfigSerializer(config, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        record(AuditLog.Action.UPDATE, request.user, config, {"fields": sorted(s.validated_data)})
        return Response(s.data)


# --- templates --------------------------------------------------------------------------------
class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReminderTemplate
        fields = ["id", "name", "subject", "body", "sms_text", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def validate_sms_text(self, value):
        if len(value) > 160:
            raise serializers.ValidationError("SMS text must be 160 characters or fewer.")
        return value


class TemplateViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    queryset = ReminderTemplate.objects.all()
    serializer_class = TemplateSerializer
    permission_classes = [IsManager]
    pagination_class = None
    search_fields = ["name", "subject"]

    def get_save_kwargs(self, created):
        return {"created_by": self.request.user} if created else {}

    @extend_schema(request=dict, responses={200: dict})
    @action(detail=False, methods=["post"])
    def preview(self, request):
        """Live preview with sample values (or `context` overrides)."""
        data = request.data or {}
        ctx = SAMPLE_CONTEXT | {k: str(v) for k, v in (data.get("context") or {}).items() if k in VARIABLES}
        return Response(
            {
                "subject": render_subject(data.get("subject", ""), ctx),
                "body": render(data.get("body", ""), ctx),
                "html": render_html(data.get("body", ""), ctx),
                "sms": sms_text(data.get("sms_text") or data.get("subject", ""), ctx),
                "sms_length": len(render(data.get("sms_text", ""), ctx)),
            }
        )

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def variables(self, request):
        return Response({"variables": [{"key": k, "label": v} for k, v in VARIABLES.items()]})


# --- rules ---------------------------------------------------------------------------------------
class RuleSerializer(serializers.ModelSerializer):
    section_name = serializers.CharField(source="section.name", read_only=True, default=None)
    template_name = serializers.CharField(source="template.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True, default=None)
    section = serializers.PrimaryKeyRelatedField(
        queryset=SidebarItem.objects.filter(item_type="page"), allow_null=True, required=False
    )

    class Meta:
        model = ReminderRule
        fields = [
            "id",
            "name",
            "section",
            "section_name",
            "trigger",
            "trigger_config",
            "channels",
            "recipients",
            "schedule",
            "template",
            "template_name",
            "attachments",
            "is_active",
            "created_by_name",
            "last_run_at",
            "next_run_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["last_run_at", "next_run_at", "created_at", "updated_at"]

    def validate_section(self, section):
        if section is not None and not can_manage(self.context["request"].user, section=section):
            raise serializers.ValidationError("You can only manage reminders for sections managers can access.")
        return section

    def validate_channels(self, value):
        if not isinstance(value, list) or not value or any(c not in CHANNELS for c in value):
            raise serializers.ValidationError(f"Choose one or more of: {', '.join(CHANNELS)}.")
        return list(dict.fromkeys(value))

    def validate_attachments(self, value):
        if not isinstance(value, list) or any(a not in ATTACHMENTS for a in value):
            raise serializers.ValidationError(f"Allowed: {', '.join(ATTACHMENTS)}.")
        return list(dict.fromkeys(value))

    def validate_recipients(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Expected an object.")
        types = value.get("types") or []
        if not types or any(t not in RECIPIENT_TYPES for t in types):
            raise serializers.ValidationError(f"Choose recipients from: {', '.join(RECIPIENT_TYPES)}.")
        emails = [e.strip() for e in value.get("emails", []) if str(e).strip()]
        for e in emails:
            serializers.EmailField().run_validation(e)
        phones = [p.strip() for p in value.get("phones", []) if str(p).strip()]
        for p in phones:
            if not __import__("re").fullmatch(r"\+?[0-9 ()-]{7,20}", p):
                raise serializers.ValidationError(f"“{p}” isn't a valid phone number.")
        if "custom" in types and not (emails or phones):
            raise serializers.ValidationError("Add at least one custom email or phone.")
        if "users" in types and not value.get("user_ids"):
            raise serializers.ValidationError("Pick at least one user.")
        return {"types": types, "user_ids": [int(i) for i in value.get("user_ids", [])], "emails": emails, "phones": phones}

    def validate_schedule(self, value):
        import re
        import zoneinfo

        if not isinstance(value, dict):
            raise serializers.ValidationError("Expected an object.")
        kind = value.get("kind", "daily")
        if kind not in ("daily", "weekly", "once", "manual"):
            raise serializers.ValidationError("kind must be daily, weekly, once or manual.")
        time = value.get("time", "09:00")
        if not re.match(HHMM, time):
            raise serializers.ValidationError("time must be HH:MM (24h).")
        tz = value.get("timezone") or settings.TIME_ZONE
        try:
            zoneinfo.ZoneInfo(tz)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError) as exc:
            raise serializers.ValidationError("Unknown timezone.") from exc
        out = {"kind": kind, "time": time, "timezone": tz}
        if kind == "weekly":
            wd = value.get("weekday", 0)
            if not str(wd).isdigit() or not 0 <= int(wd) <= 6:
                raise serializers.ValidationError("weekday must be 0 (Mon) … 6 (Sun).")
            out["weekday"] = int(wd)
        if kind == "once":
            try:
                datetime.date.fromisoformat(value.get("date", ""))
            except ValueError as exc:
                raise serializers.ValidationError("date must be YYYY-MM-DD.") from exc
            out["date"] = value["date"]
        return out

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        trigger, cfg = get("trigger"), dict(get("trigger_config") or {})
        section = get("section")
        if trigger in ("warranty_expiry", "maintenance_due", "custom_date"):
            days = cfg.get("days", [30, 7, 1] if trigger == "warranty_expiry" else [7] if trigger == "maintenance_due" else [0])
            days = days if isinstance(days, list) else [days]
            if not days or not all(str(d).lstrip("-").isdigit() and abs(int(d)) <= 3650 for d in days):
                raise serializers.ValidationError({"trigger_config": "days must be whole numbers (negative = after the date)."})
            cfg["days"] = sorted({int(d) for d in days}, reverse=True)
        if trigger == "custom_date":
            from apps.navigation.models import TableColumn

            col = cfg.get("column")
            if (
                not section
                or not TableColumn.objects.filter(sidebar_item=section, key=col, column_type="date", is_builtin=False).exists()
            ):
                raise serializers.ValidationError({"trigger_config": "Pick a custom date column of the selected section."})
        if trigger == "low_stock":
            if not str(cfg.get("threshold", 5)).isdigit():
                raise serializers.ValidationError({"trigger_config": "threshold must be a whole number."})
        if trigger == "manual" and get("schedule", {}).get("kind") != "manual":
            attrs["schedule"] = {**(get("schedule") or {}), "kind": "manual"}
        if any(a.startswith("export_") for a in get("attachments") or []) and not (section and section.table):
            raise serializers.ValidationError({"attachments": "Data exports need a section that shows a table."})
        attrs["trigger_config"] = cfg
        return attrs


class RuleViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = RuleSerializer
    permission_classes = [IsManager]
    filterset_fields = ["section", "trigger", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["name", "next_run_at", "last_run_at"]
    queryset = ReminderRule.objects.none()

    def get_queryset(self):
        qs = ReminderRule.objects.select_related("section", "template", "created_by").order_by("name")
        if effective_role(self.request.user) == "admin":
            return qs
        return qs.filter(section__visible_roles__contains=["manager"]) | qs.filter(section__isnull=True)

    def get_save_kwargs(self, created):
        return {"created_by": self.request.user} if created else {}

    def perform_create(self, serializer):
        rule = super().perform_create(serializer)
        self._schedule(rule)
        return rule

    def perform_update(self, serializer):
        rule = super().perform_update(serializer)
        self._schedule(rule)
        return rule

    @staticmethod
    def _schedule(rule):
        rule.next_run_at = compute_next_run(rule.schedule) if rule.is_active else None
        ReminderRule.objects.filter(pk=rule.pk).update(next_run_at=rule.next_run_at)

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        """Send this rule's message to yourself only (opt-outs still apply)."""
        from .tasks import run_rule

        rule = self.get_object()
        n = run_rule.apply(args=[rule.pk, "", request.user.pk]).get()
        logs = ReminderLog.objects.filter(rule=rule, is_test=True, recipient=request.user).order_by("-id")[: max(n, 3)]
        record(AuditLog.Action.UPDATE, request.user, rule, {"test_send": n})
        return Response({"queued": n, "logs": LogSerializer(logs, many=True).data})

    @extend_schema(request=None, responses={202: dict})
    @action(detail=True, methods=["post"], url_path="send-now")
    def send_now(self, request, pk=None):
        from .tasks import run_rule

        rule = self.get_object()
        tag = f"now:{timezone.now():%Y%m%d%H%M%S}:{secrets.token_hex(3)}"
        run_rule.delay(rule.pk, tag)
        record(AuditLog.Action.UPDATE, request.user, rule, {"send_now": tag})
        return Response({"queued": True, "run": tag}, status=status.HTTP_202_ACCEPTED)


# --- logs ------------------------------------------------------------------------------------
class LogSerializer(serializers.ModelSerializer):
    recipient_name = serializers.CharField(source="recipient.get_full_name", read_only=True, default=None)

    class Meta:
        model = ReminderLog
        fields = [
            "id",
            "rule",
            "rule_name",
            "recipient",
            "recipient_name",
            "recipient_address",
            "channel",
            "status",
            "subject",
            "object_ref",
            "error",
            "provider_message_id",
            "attachments",
            "attempts",
            "is_test",
            "deliver_after",
            "sent_at",
            "created_at",
        ]

    def to_representation(self, obj):
        data = super().to_representation(obj)
        data["attachments"] = [
            {"name": a.get("name"), "size": a.get("size"), "link": bool(a.get("link"))} for a in obj.attachments
        ]
        return data


class LogFilter(django_filters.FilterSet):
    date_from = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = ReminderLog
        fields = ["rule", "status", "channel", "is_test", "recipient"]


class LogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = LogSerializer
    permission_classes = [IsManager]
    filterset_class = LogFilter
    search_fields = ["recipient_address", "rule_name", "subject", "object_ref", "error"]
    ordering_fields = ["created_at", "sent_at", "status"]
    queryset = ReminderLog.objects.none()

    def get_queryset(self):
        qs = ReminderLog.objects.select_related("recipient", "rule__section")
        if effective_role(self.request.user) == "admin":
            return qs
        return qs.filter(rule__section__visible_roles__contains=["manager"]) | qs.filter(
            rule__section__isnull=True, rule__isnull=False
        )

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        from .tasks import deliver_log

        log = self.get_object()
        if log.status != ReminderLog.Status.FAILED:
            raise DomainError("Only failed sends can be retried.")
        ReminderLog.objects.filter(pk=log.pk).update(status=ReminderLog.Status.QUEUED, error="", attempts=0)
        deliver_log.delay(log.pk)
        record(AuditLog.Action.UPDATE, request.user, log, {"retry": True})
        log.refresh_from_db()
        return Response(LogSerializer(log).data)

    @action(detail=False, methods=["get"])
    def export(self, request):
        from apps.navigation.table_api import _cell

        rows = self.filter_queryset(self.get_queryset())[:20000]
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(
            ["Created", "Rule", "Channel", "Recipient", "Status", "Subject", "Attempts", "Sent at", "Provider id", "Error"]
        )
        for log in rows:
            w.writerow(
                [
                    _cell(v)
                    for v in [
                        log.created_at.isoformat(),
                        log.rule_name,
                        log.channel,
                        log.recipient_address,
                        log.status,
                        log.subject,
                        log.attempts,
                        log.sent_at.isoformat() if log.sent_at else "",
                        log.provider_message_id,
                        log.error,
                    ]
                ]
            )
        record(AuditLog.Action.EXPORT, request.user, model="reminders.reminderlog", object_repr="reminder logs (csv)")
        resp = HttpResponse(("﻿" + buf.getvalue()).encode(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="reminder-logs-{timezone.localdate():%Y%m%d}.csv"'
        return resp


# --- preferences -----------------------------------------------------------------------------
class PreferencesView(APIView):
    """The signed-in user's own notification preferences (every role)."""

    permission_classes = [IsAuthenticated]

    def _sections(self, user):
        role = effective_role(user)
        return (
            SidebarItem.objects.filter(item_type="page", is_active=True, visible_roles__contains=[role])
            .exclude(table="")
            .order_by("name")
        )

    def _payload(self, user):
        contact, _ = ContactSettings.objects.get_or_create(user=user, defaults={"timezone": settings.TIME_ZONE})
        prefs = {p.section_id: p for p in NotificationPreference.objects.filter(user=user)}
        default = prefs.get(None)
        return {
            "phone": user.phone,
            "phone_verified": contact.phone_verified,
            "quiet_start": contact.quiet_start.strftime("%H:%M") if contact.quiet_start else "",
            "quiet_end": contact.quiet_end.strftime("%H:%M") if contact.quiet_end else "",
            "timezone": contact.timezone,
            "default": {"email": default.email_enabled if default else True, "sms": default.sms_enabled if default else True},
            "sections": [
                {
                    "id": s.pk,
                    "name": s.name,
                    "email": prefs[s.pk].email_enabled if s.pk in prefs else None,
                    "sms": prefs[s.pk].sms_enabled if s.pk in prefs else None,
                }
                for s in self._sections(user)
            ],
        }

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response(self._payload(request.user))

    @extend_schema(request=dict, responses={200: dict})
    def put(self, request):
        import re
        import zoneinfo

        user, data = request.user, request.data or {}
        contact, _ = ContactSettings.objects.get_or_create(user=user)
        errors = {}
        for key in ("quiet_start", "quiet_end"):
            if key in data:
                v = data[key] or ""
                if v and not re.match(HHMM, v):
                    errors[key] = "Use HH:MM."
                else:
                    setattr(contact, key, datetime.time.fromisoformat(v) if v else None)
        if "timezone" in data:
            try:
                zoneinfo.ZoneInfo(data["timezone"])
                contact.timezone = data["timezone"]
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                errors["timezone"] = "Unknown timezone."
        if "phone" in data:
            phone = str(data["phone"] or "").strip()
            if phone and not re.fullmatch(r"\+?[0-9 ()-]{7,20}", phone):
                errors["phone"] = "Enter a valid phone number (with country code)."
            elif phone != (user.phone or ""):
                user.phone = phone
                user.save(update_fields=["phone"])
        if errors:
            raise serializers.ValidationError(errors)
        contact.save()
        allowed = set(self._sections(user).values_list("pk", flat=True))
        if isinstance(data.get("default"), dict):
            NotificationPreference.objects.update_or_create(
                user=user,
                section=None,
                defaults={
                    "email_enabled": bool(data["default"].get("email", True)),
                    "sms_enabled": bool(data["default"].get("sms", True)),
                },
            )
        for s in data.get("sections", []) or []:
            sid = s.get("id")
            if sid not in allowed:
                continue
            if s.get("email") is None and s.get("sms") is None:
                NotificationPreference.objects.filter(user=user, section_id=sid).delete()  # inherit default
                continue
            NotificationPreference.objects.update_or_create(
                user=user,
                section_id=sid,
                defaults={"email_enabled": s.get("email") is not False, "sms_enabled": s.get("sms") is not False},
            )
        record(AuditLog.Action.UPDATE, user, user, {"notification_preferences": True})
        return Response(self._payload(user))


def _hash(code: str) -> str:
    return hashlib.sha256(f"{settings.SECRET_KEY}:{code}".encode()).hexdigest()


class VerifyPhoneView(APIView):
    """POST {} → text a 6-digit code; POST {code} → confirm it."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "login"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle

        return [ScopedRateThrottle(), *super().get_throttles()]

    @extend_schema(request=dict, responses={200: dict})
    def post(self, request):
        user = request.user
        contact, _ = ContactSettings.objects.get_or_create(user=user)
        code = str((request.data or {}).get("code", "")).strip()
        if not code:
            if not user.phone:
                raise DomainError("Add a phone number first.", field="phone")
            new = f"{secrets.randbelow(10**6):06d}"
            contact.code_hash, contact.code_expires, contact.code_attempts = (
                _hash(new),
                timezone.now() + datetime.timedelta(minutes=10),
                0,
            )
            contact.save()
            config = ChannelConfig.load()
            get_sms_provider(config.sms_provider).send(
                user.phone, f"Your verification code is {new}. It expires in 10 minutes.", config.sms_sender_id
            )
            return Response({"sent": True})
        if not contact.code_hash or not contact.code_expires or contact.code_expires < timezone.now():
            raise DomainError("The code expired — request a new one.", field="code")
        if contact.code_attempts >= 5:
            raise DomainError("Too many attempts — request a new code.", field="code")
        if not secrets.compare_digest(contact.code_hash, _hash(code)):
            contact.code_attempts += 1
            contact.save(update_fields=["code_attempts"])
            raise DomainError("That code isn't right.", field="code")
        contact.verified_phone, contact.code_hash, contact.code_expires = user.phone, "", None
        contact.save()
        record(AuditLog.Action.UPDATE, user, user, {"phone_verified": True})
        return Response({"phone_verified": True})


@extend_schema(exclude=True)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def download(request, token):
    """Signed, expiring download link for large attachments (and SMS links)."""
    try:
        path = unsign_link(token)
    except signing.SignatureExpired as exc:
        raise NotFound("This link has expired.") from exc
    except signing.BadSignature as exc:
        raise PermissionDenied("Invalid link.") from exc
    if not path.startswith("reminders/") or ".." in path or not private_storage.exists(path):
        raise NotFound("File not found.")
    resp = FileResponse(private_storage.open(path, "rb"), as_attachment=True, filename=path.rsplit("/", 1)[-1])
    resp["Cache-Control"] = "private, no-store"
    return resp
