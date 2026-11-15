"""Reminder engine: schedules, trigger evaluation, recipients, preferences, attachments and queuing."""

import datetime
import uuid
import zoneinfo
from dataclasses import dataclass, field

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.core.files import private_storage
from apps.core.hosts import frontend_url
from apps.core.permissions import is_manager

from .models import ContactSettings, NotificationPreference, ReminderLog, ReminderRule

R = ReminderRule.Trigger
LINK_SALT = "reminders.download"


# --- scheduling ---------------------------------------------------------------------------
def _tz(name: str):
    try:
        return zoneinfo.ZoneInfo(name or settings.TIME_ZONE)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return zoneinfo.ZoneInfo("UTC")


def _at(day: datetime.date, hhmm: str, tz) -> datetime.datetime:
    try:
        h, m = (int(x) for x in (hhmm or "09:00").split(":")[:2])
    except ValueError:
        h, m = 9, 0
    return datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=tz)


def compute_next_run(schedule: dict, after: datetime.datetime | None = None) -> datetime.datetime | None:
    """Next run strictly after `after` (default now) for daily / weekly / once schedules; None for manual."""
    after = after or timezone.now()
    kind = (schedule or {}).get("kind", "daily")
    tz = _tz(schedule.get("timezone"))
    local = after.astimezone(tz)
    time = schedule.get("time", "09:00")
    if kind == "manual":
        return None
    if kind == "once":
        try:
            run = _at(datetime.date.fromisoformat(schedule.get("date", "")), time, tz)
        except ValueError:
            return None
        return run if run > after else None
    candidate = _at(local.date(), time, tz)
    if kind == "weekly":
        weekday = int(schedule.get("weekday", 0)) % 7
        candidate += datetime.timedelta(days=(weekday - local.weekday()) % 7)
        if candidate <= after:
            candidate += datetime.timedelta(days=7)
        return candidate
    if candidate <= after:
        candidate += datetime.timedelta(days=1)
    return candidate


# --- events ---------------------------------------------------------------------------------
@dataclass
class Event:
    key: str  # stable object key, e.g. "asset:12"
    tag: str  # what makes this occurrence unique, e.g. "2026-11-16:d7"
    context: dict
    link: str = ""
    holder: object = None
    department: object = None
    obj: object = None
    objects: list = field(default_factory=list)  # rows for export attachments


def _fmt(d) -> str:
    return d.strftime("%d %b %Y") if d else ""


def _asset_ctx(a, today, due=None) -> dict:
    holder = a.assigned_to
    return {
        "asset_name": a.name,
        "item_name": a.name,
        "asset_tag": a.asset_tag,
        "status": a.get_status_display(),
        "category": a.category.name if a.category_id else "",
        "user_name": (holder.get_full_name() or holder.email) if holder else "",
        "department": a.department.name if a.department_id else "",
        "due_date": _fmt(due),
        "days_left": (due - today).days if due else "",
    }


def section_queryset(section):
    """Live rows behind a sidebar section, used by custom-date triggers, counts and exports."""
    from apps.navigation.tables import model_for

    table = getattr(section, "table", "") if section else ""
    if table == "custom":
        from apps.navigation.models import TableRecord

        return TableRecord.objects.filter(definition__sidebar_item=section, is_archived=False)
    model = model_for(table)
    if model is None:
        from apps.assets.models import Asset

        return Asset.objects.none()
    qs = model.objects.all()
    if table == "receipts":
        qs = qs.annotate(asset_count=Count("assets", distinct=True))
    if table == "handovers":
        qs = qs.annotate(item_count=Count("items"))
    return qs


@dataclass
class TriggerContext:
    """Everything a trigger handler needs to find the events that are due for one rule run."""

    rule: ReminderRule
    now: datetime.datetime
    today: datetime.date
    since: datetime.datetime
    base: str

    @property
    def cfg(self) -> dict:
        return self.rule.trigger_config or {}

    def days(self, default: list[int]) -> list[int]:
        raw = self.cfg.get("days", default)
        raw = raw if isinstance(raw, list) else [raw]
        return sorted({int(d) for d in raw if str(d).lstrip("-").isdigit()})


def _asset_event(ctx: TriggerContext, a, tag: str, due=None) -> Event:
    return Event(
        f"asset:{a.pk}", tag, _asset_ctx(a, ctx.today, due), f"{ctx.base}/assets/{a.pk}", a.assigned_to, a.department, a, [a]
    )


def _assets_due_on(ctx: TriggerContext, date_field: str, default_days: list[int]):
    from apps.assets.models import Asset

    for d in ctx.days(default_days):
        due = ctx.today + datetime.timedelta(days=d)
        qs = (
            Asset.objects.filter(**{date_field: due})
            .exclude(status__in=["retired", "lost"])
            .select_related("assigned_to", "department", "category")
        )
        for a in qs:
            yield _asset_event(ctx, a, f"{due.isoformat()}:d{d}", due)


def _warranty_expiry(ctx: TriggerContext):
    return _assets_due_on(ctx, "warranty_expiry", [30, 7, 1])


def _maintenance_due(ctx: TriggerContext):
    return _assets_due_on(ctx, "next_maintenance_date", [7])


def _overdue_return(ctx: TriggerContext):
    from apps.workflows.models import Handover

    qs = Handover.objects.filter(type="issue", status="completed", expected_return_date__lt=ctx.today).select_related(
        "to_user", "to_department"
    )
    for h in qs:
        still_out = list(
            h.items.filter(asset__status="assigned")
            .filter(Q(asset__assigned_to=h.to_user) if h.to_user_id else Q(asset__department=h.to_department))
            .select_related("asset")
        )
        if not still_out:
            continue
        context = _asset_ctx(still_out[0].asset, ctx.today, h.expected_return_date) | {
            "reference": h.reference,
            "count": len(still_out),
        }
        yield Event(
            f"handover:{h.pk}",
            ctx.today.isoformat(),
            context,
            f"{ctx.base}/handovers/{h.pk}",
            h.to_user,
            h.to_department,
            h,
            [i.asset for i in still_out],
        )


def _handover_pending(ctx: TriggerContext):
    from apps.workflows.models import Handover

    cutoff = ctx.now - datetime.timedelta(hours=int(ctx.cfg.get("min_age_hours", 24) or 0))
    for h in Handover.objects.filter(status="pending", created_at__lte=cutoff).select_related("signer"):
        context = {
            "reference": h.reference,
            "item_name": h.reference,
            "user_name": h.signer.get_full_name() if h.signer else "",
            "status": h.get_status_display(),
            "count": h.items.count(),
        }
        yield Event(f"handover:{h.pk}", ctx.today.isoformat(), context, f"{ctx.base}/handovers/{h.pk}", h.signer, None, h, [h])


def _new_receipt(ctx: TriggerContext):
    from apps.workflows.models import GoodsReceipt

    for r in GoodsReceipt.objects.filter(created_at__gt=ctx.since).select_related("vendor"):
        context = {
            "reference": r.reference,
            "item_name": r.reference,
            "count": r.assets.count(),
            "due_date": _fmt(r.received_date),
        }
        yield Event(f"receipt:{r.pk}", "new", context, f"{ctx.base}/receiving/{r.pk}", None, None, r, [r])


def _low_stock(ctx: TriggerContext):
    from apps.assets.models import Category

    threshold = int(ctx.cfg.get("threshold", 5) or 0)
    cats = Category.objects.filter(is_active=True)
    if ctx.cfg.get("category"):
        cats = cats.filter(pk=ctx.cfg["category"])
    for c in cats.annotate(stock=Count("assets", filter=Q(assets__status="in_stock"))).filter(stock__lt=threshold):
        context = {"category": c.name, "item_name": c.name, "count": c.stock}
        link = f"{ctx.base}/assets?category={c.pk}&status=in_stock"
        yield Event(f"category:{c.pk}", ctx.today.isoformat(), context, link, None, None, c, [])


def _status_change(ctx: TriggerContext):
    from apps.assets.models import AssetEvent

    events = (
        AssetEvent.objects.filter(created_at__gt=ctx.since)
        .exclude(to_status="")
        .select_related("asset", "asset__assigned_to", "asset__department", "asset__category")
    )
    if ctx.cfg.get("to_status"):
        events = events.filter(to_status=ctx.cfg["to_status"])
    for e in events:
        if e.from_status != e.to_status:
            yield _asset_event(ctx, e.asset, f"event{e.pk}")


def _custom_date(ctx: TriggerContext):
    column, section = ctx.cfg.get("column", ""), ctx.rule.section
    if not column:
        return
    path = section.route if section else ""
    for d in ctx.days([0]):
        due = ctx.today + datetime.timedelta(days=d)
        for row in section_queryset(section).filter(**{f"custom_data__{column}": due.isoformat()}):
            name = getattr(row, "name", "") or (row.custom_data or {}).get("name", "") or f"#{row.pk}"
            holder = getattr(row, "assigned_to", None)
            context = {
                "item_name": name,
                "asset_name": name,
                "asset_tag": getattr(row, "asset_tag", ""),
                "due_date": _fmt(due),
                "days_left": d,
                "user_name": holder.get_full_name() if holder else "",
            }
            yield Event(
                f"{row._meta.model_name}:{row.pk}",
                f"{due.isoformat()}:d{d}",
                context,
                f"{ctx.base}{path}",
                holder,
                getattr(row, "department", None),
                row,
                [row],
            )


def _manual(ctx: TriggerContext):
    section = ctx.rule.section
    rows = list(section_queryset(section)[:20000])
    yield Event(
        "section", "manual", {"count": len(rows)}, f"{ctx.base}{section.route if section else ''}", None, None, None, rows
    )


# Trigger -> handler yielding the Events due now. Add a trigger by adding a handler here (open/closed).
TRIGGER_HANDLERS = {
    R.WARRANTY_EXPIRY: _warranty_expiry,
    R.MAINTENANCE_DUE: _maintenance_due,
    R.OVERDUE_RETURN: _overdue_return,
    R.HANDOVER_PENDING: _handover_pending,
    R.NEW_RECEIPT: _new_receipt,
    R.LOW_STOCK: _low_stock,
    R.STATUS_CHANGE: _status_change,
    R.CUSTOM_DATE: _custom_date,
    R.MANUAL: _manual,
}


def events_for(rule: ReminderRule, now: datetime.datetime | None = None) -> list[Event]:
    now = now or timezone.now()
    ctx = TriggerContext(
        rule=rule,
        now=now,
        today=now.astimezone(_tz((rule.schedule or {}).get("timezone"))).date(),
        since=rule.last_run_at or (now - datetime.timedelta(days=1)),
        base=frontend_url(),
    )
    handler = TRIGGER_HANDLERS.get(rule.trigger)
    out = list(handler(ctx)) if handler else []
    section = rule.section
    section_name = getattr(getattr(section, "definition", None), "name", "") if section else ""
    shared = {"section_name": section_name or (section.name if section else ""), "org_name": settings.ORG_NAME}
    for ev in out:
        ev.context = shared | {"link": ev.link} | ev.context
    return out


# --- recipients -------------------------------------------------------------------------
@dataclass
class Recipient:
    user: object = None
    email: str = ""
    phone: str = ""

    @property
    def key(self) -> str:
        return f"u{self.user.pk}" if self.user else (self.email or self.phone)


def recipients_for(rule: ReminderRule, event: Event) -> list[Recipient]:
    User = get_user_model()
    spec = rule.recipients or {}
    types = set(spec.get("types", []))
    users: dict[int, object] = {}
    if "holder" in types and event.holder is not None and getattr(event.holder, "is_active", False):
        users[event.holder.pk] = event.holder
    if "department_head" in types and event.department is not None and event.department.head_id:
        head = event.department.head
        if head.is_active:
            users[head.pk] = head
    if "managers" in types:
        for u in User.objects.filter(is_active=True, role__in=["admin", "manager"]):
            users[u.pk] = u
    if "users" in types:
        for u in User.objects.filter(is_active=True, pk__in=[int(i) for i in spec.get("user_ids", []) if str(i).isdigit()]):
            users[u.pk] = u
    out = [Recipient(user=u, email=u.email, phone=(u.phone or "").strip()) for u in users.values()]
    if "custom" in types:
        out += [Recipient(email=e.strip()) for e in spec.get("emails", []) if e and "@" in e]
        out += [Recipient(phone=p.strip()) for p in spec.get("phones", []) if p and p.strip()]
    return out


def channel_allowed(user, section, channel: str) -> tuple[bool, str]:
    """User opt-outs (section-specific, else global default) and phone verification."""
    if user is None:
        return True, ""
    if channel == "in_app":
        return True, ""
    scope = Q(section__isnull=True) | (Q(section=section) if section is not None else Q(pk__in=[]))
    prefs = {p.section_id: p for p in NotificationPreference.objects.filter(scope, user=user)}
    pref = prefs.get(getattr(section, "pk", None)) or prefs.get(None)
    if pref is not None and not getattr(pref, f"{channel}_enabled"):
        return False, f"{channel} turned off by the user"
    if channel == "sms":
        contact = ContactSettings.objects.filter(user=user).first()
        if not (contact and contact.phone_verified):
            return False, "phone number not verified"
    return True, ""


def quiet_until(user, now: datetime.datetime) -> datetime.datetime | None:
    """End of the user's quiet hours if `now` falls inside them, else None."""
    contact = ContactSettings.objects.filter(user=user).first() if user else None
    if not (contact and contact.quiet_start and contact.quiet_end):
        return None
    tz = _tz(contact.timezone)
    local = now.astimezone(tz)
    start, end, t = contact.quiet_start, contact.quiet_end, local.time()
    inside = (start <= t < end) if start < end else (t >= start or t < end)
    if not inside:
        return None
    end_dt = datetime.datetime.combine(local.date(), end, tzinfo=tz)
    if end_dt <= local:
        end_dt += datetime.timedelta(days=1)
    return end_dt


# --- attachments -------------------------------------------------------------------------
def signed_link(path: str) -> str:
    # URL-safe (no "/"), tamper-proof and time-limited.
    token = signing.dumps(path, salt=LINK_SALT, compress=True)
    return f"{frontend_url()}/api/reminders/download/{token}/"


def unsign_link(token: str) -> str:
    return signing.loads(token, salt=LINK_SALT, max_age=settings.REMINDER_LINK_HOURS * 3600)


def _store(name: str, content: bytes) -> str:
    return private_storage.save(f"reminders/{uuid.uuid4().hex}/{name}", ContentFile(content))


def build_attachments(rule: ReminderRule, event: Event) -> list[dict]:
    """Generate the rule's attachments for one event and store them privately.

    Returns [{name, path, size, mimetype, link?}]. If the total exceeds the size limit, every file is sent
    as a signed, expiring download link instead of an attachment.
    """
    from apps.core.pdf import handover_pdf, receipt_pdf
    from apps.navigation.table_api import build_export, effective_columns
    from apps.workflows.models import GoodsReceipt, Handover

    files: list[tuple[str, bytes, str]] = []
    kinds = set(rule.attachments or [])
    obj = event.obj
    if "bill" in kinds:
        bill_holder = obj if hasattr(obj, "invoice_file") else None
        if bill_holder is None and isinstance(obj, Handover):
            first = obj.items.select_related("asset").first()
            bill_holder = first.asset if first else None
        if bill_holder is not None:
            f = bill_holder.invoice_file
            if not f and getattr(bill_holder, "receipt", None) is not None and bill_holder.receipt.invoice_file:
                f = bill_holder.receipt.invoice_file
            if f:
                with f.open("rb") as fh:
                    content = fh.read()
                ext = f.name.rsplit(".", 1)[-1].lower()
                files.append(
                    (f"bill-{event.key.replace(':', '-')}.{ext}", content, "application/pdf" if ext == "pdf" else f"image/{ext}")
                )
            elif isinstance(bill_holder, GoodsReceipt):
                files.append((f"{bill_holder.reference}.pdf", receipt_pdf(bill_holder), "application/pdf"))
    if "receipt_pdf" in kinds:
        if isinstance(obj, Handover):
            files.append((f"{obj.reference}.pdf", handover_pdf(obj), "application/pdf"))
        elif isinstance(obj, GoodsReceipt):
            files.append((f"{obj.reference}.pdf", receipt_pdf(obj), "application/pdf"))
        elif obj is not None and hasattr(obj, "handover_items"):
            item = (
                obj.handover_items.filter(handover__status="completed")
                .select_related("handover")
                .order_by("-handover__completed_at")
                .first()
            )
            if item:
                files.append((f"{item.handover.reference}.pdf", handover_pdf(item.handover), "application/pdf"))
    export_kinds = [k.split("_", 1)[1] for k in kinds if k.startswith("export_")]
    if export_kinds and rule.section and rule.section.table:
        creator = rule.created_by
        cols = [c for c in effective_columns(rule.section, rule.section.table, creator) if c["visible"]] if creator else []
        if cols:
            for fmt in sorted(export_kinds):
                content, mimetype, ext = build_export(rule.section.table, cols, event.objects, fmt)
                files.append((f"{rule.section.name.lower().replace(' ', '-')}-export.{ext}", content, mimetype))
    out, total = [], 0
    for name, content, mimetype in files:
        path = _store(name, content)
        total += len(content)
        out.append({"name": name, "path": path, "size": len(content), "mimetype": mimetype})
    if total > settings.REMINDER_ATTACHMENT_MAX_MB * 1024 * 1024:
        for a in out:
            a["link"] = signed_link(a["path"])
            a["too_large"] = True
    return out


# --- queuing -----------------------------------------------------------------------------------
def queue_rule(
    rule: ReminderRule, *, run_tag: str = "", test_user=None, now: datetime.datetime | None = None
) -> list[ReminderLog]:
    """Create one log per (event, recipient, channel), idempotently. Returns new logs to deliver."""
    from .models import ChannelConfig
    from .templating import render, render_html, render_subject, sms_text

    now = now or timezone.now()
    config = ChannelConfig.load()
    template = rule.template
    channels = [c for c in rule.channels if c in ("email", "sms", "in_app")]
    channels = [c for c in channels if getattr(config, f"{c}_enabled")]
    events = events_for(rule, now)
    if test_user is not None:
        if not events:  # nothing matches right now: preview with sample values so the message reads naturally
            from .templating import SAMPLE_CONTEXT

            section_name = rule.section.name if rule.section else ""
            sample = SAMPLE_CONTEXT | {"org_name": settings.ORG_NAME, "section_name": section_name, "link": frontend_url()}
            events = [Event("test", "test", sample, frontend_url())]
        events = events[:1]
    created: list[ReminderLog] = []
    for ev in events:
        recipients = (
            [Recipient(user=test_user, email=test_user.email, phone=(test_user.phone or "").strip())]
            if test_user
            else recipients_for(rule, ev)
        )
        attachments = None
        for rcpt in recipients:
            ctx = ev.context | {"recipient_name": (rcpt.user.get_full_name() if rcpt.user else rcpt.email or rcpt.phone)}
            for channel in channels:
                address = (
                    rcpt.email
                    if channel == "email"
                    else rcpt.phone
                    if channel == "sms"
                    else (str(rcpt.user.pk) if rcpt.user else "")
                )
                if not address:
                    continue
                suffix = f"test:{uuid.uuid4().hex[:8]}" if test_user else (run_tag or ev.tag)
                key = f"r{rule.pk}:{ev.key}:{suffix}:{rcpt.key}:{channel}"[:255]
                if ReminderLog.objects.filter(dedupe_key=key).exists():
                    continue
                allowed, reason = channel_allowed(rcpt.user, rule.section, channel)
                if attachments is None and allowed and channel in ("email", "sms"):
                    attachments = build_attachments(rule, ev) if rule.attachments else []
                links = (
                    " ".join(a["link"] if a.get("link") else signed_link(a["path"]) for a in (attachments or []))
                    if channel == "sms"
                    else ""
                )
                log = ReminderLog(
                    rule=rule,
                    rule_name=rule.name,
                    recipient=rcpt.user,
                    recipient_address=address,
                    channel=channel,
                    subject=render_subject(template.subject, ctx),
                    message=sms_text(template.sms_text or template.subject, ctx, links.split(" ")[0] if links else "")
                    if channel != "email"
                    else render(template.body, ctx),
                    html=render_html(template.body, ctx) if channel == "email" else "",
                    object_ref=ev.key,
                    link=ev.link,
                    attachments=(attachments or []) if channel == "email" else [],
                    dedupe_key=key,
                    is_test=test_user is not None,
                    status=ReminderLog.Status.QUEUED if allowed else ReminderLog.Status.SKIPPED,
                    error="" if allowed else reason,
                    deliver_after=quiet_until(rcpt.user, now) if (allowed and channel != "in_app") else None,
                )
                try:
                    with transaction.atomic():
                        log.save()
                except IntegrityError:  # another worker queued it first
                    continue
                if allowed:
                    created.append(log)
    return created


def can_manage(user, rule: ReminderRule | None = None, section=None) -> bool:
    """Admins manage everything; managers manage rules for sections visible to managers."""
    if user.is_superuser or user.role == "admin":
        return True
    if not is_manager(user):
        return False
    section = section if section is not None else getattr(rule, "section", None)
    return section is None or "manager" in (section.visible_roles or [])
