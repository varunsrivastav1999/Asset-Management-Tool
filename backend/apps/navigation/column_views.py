import re

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import AuditedViewSetMixin, record
from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdmin, is_admin
from apps.core.roles import validate_roles

from .models import SidebarItem, TableColumn, TablePreference
from .table_api import clean_options, effective_columns, resolve_item
from .tables import TABLES, ensure_columns

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
CUSTOM_TYPES = [t for t in TableColumn.Type.values if t != "auto_number"]


class TableColumnSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(source="column_type", choices=TableColumn.Type.choices, required=False)
    key = serializers.CharField(max_length=64, required=False)

    class Meta:
        model = TableColumn
        fields = [
            "id",
            "sidebar_item",
            "name",
            "key",
            "type",
            "options",
            "width",
            "order",
            "is_visible",
            "is_required",
            "is_searchable",
            "is_sortable",
            "is_builtin",
            "visible_roles",
            "updated_at",
        ]
        read_only_fields = ["is_builtin", "updated_at"]
        validators = []  # key is derived from the name and checked for uniqueness in validate()

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate_visible_roles(self, value):
        return validate_roles(value)

    def validate_width(self, value):
        if value is not None and not 40 <= value <= 800:
            raise serializers.ValidationError("Width must be between 40 and 800 px.")
        return value

    def validate_sidebar_item(self, item):
        if item.item_type != SidebarItem.Type.PAGE or item.table not in TABLES:
            raise serializers.ValidationError("Columns can only be added to sidebar pages that show a table.")
        return item

    def validate(self, attrs):
        inst = self.instance
        if inst and inst.is_builtin:
            # Built-ins: label, order, width, visibility, roles and search/sort toggles only.
            for locked in ("key", "column_type", "options", "sidebar_item"):
                if locked in attrs and attrs[locked] != getattr(inst, locked):
                    raise serializers.ValidationError({locked: "Built-in columns can't change this."})
            if attrs.get("is_sortable") and not inst.is_sortable and not _builtin_sortable(inst):
                raise serializers.ValidationError({"is_sortable": "This built-in column can't be sorted."})
            if attrs.get("is_searchable") and not _builtin_searchable(inst):
                raise serializers.ValidationError({"is_searchable": "This built-in column can't be searched."})
            return attrs
        item = attrs.get("sidebar_item") or getattr(inst, "sidebar_item", None)
        if item is None:
            raise serializers.ValidationError({"sidebar_item": "Required."})
        table = TABLES[item.table]
        if not table.supports_custom:
            raise serializers.ValidationError({"sidebar_item": f"{table.label} doesn't support custom columns."})
        kind = attrs.get("column_type") or getattr(inst, "column_type", TableColumn.Type.TEXT)
        if kind not in CUSTOM_TYPES:
            raise serializers.ValidationError({"type": f"Custom columns can be: {', '.join(CUSTOM_TYPES)}."})
        attrs["column_type"] = kind
        key = attrs.get("key") or getattr(inst, "key", None) or _slug(attrs.get("name", ""))
        if not KEY_RE.match(key or ""):
            raise serializers.ValidationError({"key": "Use lowercase letters, digits and underscores, starting with a letter."})
        if key in {c.key for c in table.columns}:
            raise serializers.ValidationError({"key": "That key is reserved by a built-in column."})
        clash = TableColumn.objects.filter(sidebar_item=item, key=key)
        if inst:
            clash = clash.exclude(pk=inst.pk)
        if clash.exists():
            raise serializers.ValidationError({"key": "A column with this key already exists on this page."})
        attrs["key"] = key
        options = attrs.get("options", getattr(inst, "options", []))
        attrs["options"] = clean_options(kind, options)
        return attrs


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return (s if s[:1].isalpha() else f"col_{s}")[:64] if s else ""


def _builtin_sortable(col):
    from .tables import builtin

    b = builtin(col.sidebar_item.table, col.key)
    return bool(b and b.sort is not None)


def _builtin_searchable(col):
    from .tables import builtin

    b = builtin(col.sidebar_item.table, col.key)
    return bool(b and b.search)


class TableColumnViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    """Admin-only column configuration."""

    queryset = TableColumn.objects.select_related("sidebar_item").order_by("sidebar_item_id", "order", "id")
    serializer_class = TableColumnSerializer
    permission_classes = [IsAdmin]
    pagination_class = None
    filterset_fields = ["sidebar_item", "is_builtin"]

    def perform_create(self, serializer):
        item = serializer.validated_data["sidebar_item"]
        if "order" not in serializer.validated_data:
            last = TableColumn.objects.filter(sidebar_item=item).order_by("-order").values_list("order", flat=True).first()
            serializer.validated_data["order"] = (last if last is not None else -1) + 1
        return super().perform_create(serializer)

    def perform_destroy(self, instance):
        if instance.is_builtin:
            raise DomainError("Built-in columns can't be deleted — hide them instead.")
        super().perform_destroy(instance)

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["post"])
    def reorder(self, request):
        item = _item_from(request.data.get("sidebar_item"))
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            raise DomainError("ids must be a list of column ids.", field="ids")
        with transaction.atomic():
            cols = {c.pk: c for c in TableColumn.objects.select_for_update().filter(sidebar_item=item)}
            if len(ids) != len(set(ids)) or set(ids) != set(cols):
                raise DomainError("Provide every column id of this page exactly once.", field="ids")
            for pos, pk in enumerate(ids):
                cols[pk].order = pos
            TableColumn.objects.bulk_update(cols.values(), ["order"])
        record(AuditLog.Action.BULK_UPDATE, request.user, item, {"column_order": ids})
        _broadcast(item.pk)
        return Response({"updated": len(ids)})

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["post"])
    def reset(self, request):
        item = _item_from(request.data.get("sidebar_item"))
        with transaction.atomic():
            TableColumn.objects.filter(sidebar_item=item).delete()
            ensure_columns(item)
        record(AuditLog.Action.BULK_UPDATE, request.user, item, {"columns": "reset to defaults"})
        _broadcast(item.pk)
        return Response({"columns": TableColumn.objects.filter(sidebar_item=item).count()})


def _item_from(raw):
    try:
        item = SidebarItem.objects.get(pk=int(raw))
    except (SidebarItem.DoesNotExist, TypeError, ValueError) as exc:
        raise DomainError("Unknown sidebar page.", field="sidebar_item") from exc
    if item.table not in TABLES:
        raise DomainError("That sidebar item has no table.", field="sidebar_item")
    return item


def _broadcast(item_id):
    from .signals import broadcast_columns_change

    broadcast_columns_change(item_id)


@extend_schema(responses={200: dict})
@api_view(["GET"])
def tables(request):
    """Registry of table definitions (used by the sidebar editor's table picker)."""
    return Response(
        {
            "tables": [
                {"key": t.key, "label": t.label, "route": t.route, "supports_custom": t.supports_custom} for t in TABLES.values()
            ],
            "column_types": [{"value": v, "label": label} for v, label in TableColumn.Type.choices if v in CUSTOM_TYPES],
        }
    )


@extend_schema(responses={200: dict})
@api_view(["GET"])
def table_columns(request, table):
    """Effective columns for one table page (role-filtered, with this user's visibility)."""
    if table not in TABLES:
        return Response({"detail": "Unknown table."}, status=status.HTTP_404_NOT_FOUND)
    item = resolve_item(table, request.query_params.get("item"))
    return Response(
        {
            "key": table,
            "item": item.pk if item else None,
            "supports_custom": TABLES[table].supports_custom,
            "can_edit": is_admin(request.user),
            "columns": effective_columns(item, table, request.user),
        }
    )


class PrefSerializer(serializers.Serializer):
    item = serializers.PrimaryKeyRelatedField(queryset=SidebarItem.objects.exclude(table=""))
    hidden = serializers.ListField(child=serializers.CharField(max_length=64), max_length=100)
    shown = serializers.ListField(child=serializers.CharField(max_length=64), max_length=100)


@extend_schema(request=PrefSerializer, responses={200: dict})
@api_view(["PUT", "DELETE"])
def table_prefs(request):
    """Save (PUT) or clear (DELETE ?item=) the current user's own column visibility. Any role."""
    if request.method == "DELETE":
        TablePreference.objects.filter(user=request.user, sidebar_item_id=request.query_params.get("item")).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    s = PrefSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    item = s.validated_data["item"]
    ensure_columns(item)
    keys = set(item.columns.values_list("key", flat=True))
    required = set(item.columns.filter(is_required=True).values_list("key", flat=True))
    hidden = [k for k in dict.fromkeys(s.validated_data["hidden"]) if k in keys and k not in required]
    shown = [k for k in dict.fromkeys(s.validated_data["shown"]) if k in keys and k not in hidden]
    TablePreference.objects.update_or_create(user=request.user, sidebar_item=item, defaults={"hidden": hidden, "shown": shown})
    record(AuditLog.Action.UPDATE, request.user, item, {"my_columns": {"hidden": hidden, "shown": shown}})
    return Response(
        {"item": item.pk, "hidden": hidden, "shown": shown, "columns": effective_columns(item, item.table, request.user)}
    )
