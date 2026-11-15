"""CRUD for table definitions (incl. admin-created custom tables) and their records."""

import re

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import AuditedViewSetMixin, record, snapshot
from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdmin, ReadAnyWriteAdmin, is_admin, is_manager
from apps.core.roles import effective_role, validate_roles

from .definitions import unique_slug
from .models import SidebarItem, TableColumn, TableDefinition, TableRecord
from .serializers import ICON_RE
from .signals import broadcast_sidebar_change
from .table_api import ConfigurableTableMixin, clean_options, coerce_value
from .tables import TABLES, ensure_columns, model_for

CUSTOM = TableDefinition.CUSTOM


def row_count(defn: TableDefinition) -> int:
    """Live (non-archived) rows behind a table."""
    if defn.source == CUSTOM:
        return defn.records.filter(is_archived=False).count()
    model = model_for(defn.source)
    if model is None:
        return 0
    qs = model.objects.all()
    if defn.source == "assets":
        qs = qs.exclude(status="retired")  # retired = archived
    if defn.source == "users":
        qs = qs.filter(is_active=True)
    return qs.count()


def delete_blocker(defn: TableDefinition, deleting=()) -> str | None:
    """Why `defn` can't be deleted, or None.

    Built-in data (assets, people…) isn't owned by one page: another menu page showing the same table keeps it
    reachable, so only the last page of a built-in table is protected. `deleting` lists definition ids removed in
    the same operation (e.g. a whole menu group), which don't count as "another page".
    """
    if defn.source != CUSTOM:
        others = TableDefinition.objects.filter(source=defn.source).exclude(pk=defn.pk).exclude(pk__in=list(deleting))
        if others.exists():
            return None
    n = row_count(defn)
    if not n:
        return None
    if defn.source == CUSTOM:
        return f"“{defn.name}” still has {n} record(s). Archive them or move them to another table first."
    return f"“{defn.name}” still has {n} active row(s). Archive (retire/deactivate) or move them before deleting this table."


class ColumnSeedSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=60)
    type = serializers.ChoiceField(choices=[t for t in TableColumn.Type.values if t != "auto_number"], default="text")
    options = serializers.ListField(child=serializers.CharField(max_length=80), required=False, default=list)


class TableDefinitionSerializer(serializers.ModelSerializer):
    route = serializers.CharField(source="sidebar_item.route", read_only=True)
    parent = serializers.PrimaryKeyRelatedField(
        queryset=SidebarItem.objects.filter(item_type=SidebarItem.Type.GROUP), required=False, allow_null=True, write_only=True
    )
    visible_roles = serializers.ListField(child=serializers.CharField(), required=False, write_only=True)
    columns = ColumnSeedSerializer(many=True, required=False, write_only=True)
    row_count = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = TableDefinition
        fields = [
            "id",
            "name",
            "singular",
            "icon",
            "description",
            "source",
            "slug",
            "sidebar_item",
            "route",
            "parent",
            "visible_roles",
            "roles",
            "columns",
            "row_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["source", "slug", "sidebar_item", "created_at", "updated_at"]

    def get_row_count(self, obj) -> int:
        return row_count(obj)

    def get_roles(self, obj) -> list[str]:
        return obj.sidebar_item.visible_roles

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Use at least 2 characters.")
        qs = TableDefinition.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A table with this name already exists.")
        return value

    def validate_singular(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Singular name is required.")
        return value

    def validate_icon(self, value):
        value = (value or "").strip()
        if value and not ICON_RE.match(value):
            raise serializers.ValidationError("Use a lowercase icon name such as 'boxes'.")
        return value

    def validate_visible_roles(self, value):
        return validate_roles(value)

    def validate_columns(self, cols):
        names = [c["name"].strip().lower() for c in cols]
        if len(names) != len(set(names)):
            raise serializers.ValidationError("Column names must be unique.")
        for c in cols:
            try:
                c["options"] = clean_options(c["type"], c.get("options", []))
            except serializers.ValidationError as exc:
                raise serializers.ValidationError(f"“{c['name']}”: {exc.detail['options']}")
        return cols


def _key(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "col"
    base = base if base[0].isalpha() else f"col_{base}"
    key, i = base[:60], 2
    while key in taken:
        key, i = f"{base[:56]}_{i}", i + 1
    return key


class TableDefinitionViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    """Tables behind sidebar pages. Everyone may read the ones they can see; only admins change them."""

    serializer_class = TableDefinitionSerializer
    permission_classes = [ReadAnyWriteAdmin]
    pagination_class = None
    filterset_fields = ["source", "slug"]
    search_fields = ["name", "singular", "description"]

    def get_queryset(self):
        qs = TableDefinition.objects.select_related("sidebar_item").order_by("name")
        if is_admin(self.request.user):
            return qs
        role = effective_role(self.request.user)
        return qs.filter(sidebar_item__is_active=True, sidebar_item__visible_roles__contains=[role])

    @transaction.atomic
    def perform_create(self, serializer):
        data = serializer.validated_data
        columns = data.pop("columns", [])
        parent = data.pop("parent", None)
        roles = data.pop("visible_roles", ["admin", "manager", "employee"])
        slug = unique_slug(TableDefinition, data["name"])
        last = SidebarItem.objects.filter(parent=parent).order_by("-order").values_list("order", flat=True).first()
        item = SidebarItem.objects.create(
            name=data["name"],
            item_type=SidebarItem.Type.PAGE,
            route=f"/t/{slug}",
            icon=data.get("icon") or "list",
            parent=parent,
            order=(last if last is not None else -1) + 1,
            visible_roles=roles,
            table=CUSTOM,
        )
        defn = serializer.save(sidebar_item=item, source=CUSTOM, slug=slug)
        ensure_columns(item)
        cols = columns or [{"name": "Name", "type": "text", "options": []}]
        taken = {c.key for c in TABLES[CUSTOM].columns}
        # Order: S.No, the table's own columns, then the Created/Updated built-ins.
        for i, c in enumerate(cols, start=1):
            key = _key(c["name"], taken)
            taken.add(key)
            TableColumn.objects.create(
                sidebar_item=item,
                name=c["name"].strip(),
                key=key,
                column_type=c["type"],
                options=c["options"],
                order=i,
                is_required=i == 1,
                is_searchable=c["type"] in ("text", "select", "status", "user"),
                is_sortable=c["type"] != "file",
            )
        for j, key in enumerate(("created_at", "updated_at")):
            TableColumn.objects.filter(sidebar_item=item, key=key).update(order=len(cols) + 1 + j)
        record(AuditLog.Action.CREATE, self.request.user, defn, {"after": snapshot(defn), "columns": [c["name"] for c in cols]})
        broadcast_sidebar_change()
        return defn

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        defn = self.perform_create(serializer)
        return Response(self.get_serializer(defn).data, status=status.HTTP_201_CREATED)

    @transaction.atomic
    def perform_update(self, serializer):
        data = serializer.validated_data
        has_parent = "parent" in data
        parent = data.pop("parent", None)
        roles = data.pop("visible_roles", None)
        data.pop("columns", None)
        before = snapshot(serializer.instance)
        defn = serializer.save()
        # The sidebar entry mirrors the table's name and icon.
        item_updates = {"name": defn.name}
        if defn.icon:
            item_updates["icon"] = defn.icon
        if roles is not None:
            item_updates["visible_roles"] = roles
        if has_parent:
            item_updates["parent"] = parent
        SidebarItem.objects.filter(pk=defn.sidebar_item_id).update(**item_updates)
        changes = {k: v for k, v in snapshot(defn).items() if before.get(k) != v}
        if changes or roles is not None:
            record(AuditLog.Action.UPDATE, self.request.user, defn, {"changes": changes, "roles": roles})
        broadcast_sidebar_change()
        return defn

    def perform_destroy(self, instance):
        blocker = delete_blocker(instance)
        if blocker:
            raise DomainError(blocker, code="has_data")
        repr_, pk, before = str(instance), instance.pk, snapshot(instance)
        with transaction.atomic():
            # Keep any archived rows of a custom table, labelled with where they came from.
            instance.records.update(archived_from=instance.name, is_archived=True)
            instance.sidebar_item.delete()  # cascades definition, columns and preferences
        record(
            AuditLog.Action.DELETE,
            self.request.user,
            model="navigation.tabledefinition",
            object_id=pk,
            object_repr=repr_,
            changes={"before": before},
        )
        broadcast_sidebar_change()

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"], url_path="delete-check", permission_classes=[IsAdmin])
    def delete_check(self, request, pk=None):
        defn = self.get_object()
        blocker = delete_blocker(defn)
        return Response({"can_delete": blocker is None, "reason": blocker, "row_count": row_count(defn)})


# --- records ---------------------------------------------------------------------------
class TableRecordSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True, default=None)

    class Meta:
        model = TableRecord
        fields = ["id", "custom_data", "is_archived", "created_by_name", "created_at", "updated_at"]
        read_only_fields = ["is_archived", "created_at", "updated_at"]

    def validate_custom_data(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object of {column_key: value}.")
        columns = {c.key: c for c in self.context["columns"] if not c.is_builtin}
        unknown = [k for k in data if k not in columns]
        if unknown:
            raise serializers.ValidationError(f"Unknown column(s): {', '.join(unknown)}.")
        merged = dict(self.instance.custom_data) if self.instance else {}
        errors = {}
        for key, raw in data.items():
            try:
                value = coerce_value(columns[key], raw)
            except DomainError as exc:
                errors[key] = exc.message
                continue
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        for key, col in columns.items():
            if col.is_required and merged.get(key) in (None, ""):
                errors[key] = f"{col.name} is required."
        if errors:
            raise serializers.ValidationError(errors)
        return merged


class TableRecordViewSet(ConfigurableTableMixin, viewsets.ModelViewSet):
    """Rows of a custom table. `?table_item=<sidebar item id>` selects the table (required)."""

    table_key = CUSTOM
    serializer_class = TableRecordSerializer
    permission_classes = [IsAuthenticated]
    queryset = TableRecord.objects.none()
    ordering_fields = ["created_at", "updated_at"]

    def table_item(self):
        if not hasattr(self, "_table_item"):
            raw = self.request.query_params.get("table_item")
            item = SidebarItem.objects.filter(pk=raw, table=CUSTOM).first() if str(raw or "").isdigit() else None
            if item is None:
                raise NotFound("Unknown table.")
            role = effective_role(self.request.user)
            if not is_admin(self.request.user) and (not item.is_active or role not in item.visible_roles):
                raise NotFound("Unknown table.")
            self._table_item = item
        return self._table_item

    def get_permissions(self):
        perms = super().get_permissions()
        if self.request.method not in ("GET", "HEAD", "OPTIONS") and self.action not in ("export_table",):
            if not is_manager(self.request.user):
                self.permission_denied(self.request, message="Manager or administrator role required.")
        return perms

    def get_queryset(self):
        item = self.table_item()
        archived = self.request.query_params.get("archived") in ("1", "true") and is_manager(self.request.user)
        return (
            TableRecord.objects.filter(definition__sidebar_item=item, is_archived=archived)
            .select_related("created_by")
            .order_by("-created_at", "-id")
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.action in ("create", "update", "partial_update"):
            item = self.table_item()
            ensure_columns(item)
            ctx["columns"] = list(item.columns.all())
        return ctx

    def perform_create(self, serializer):
        defn = self.table_item().definition
        rec = serializer.save(definition=defn, created_by=self.request.user)
        record(AuditLog.Action.CREATE, self.request.user, rec, {"table": defn.name, "after": rec.custom_data})

    def perform_update(self, serializer):
        before = dict(serializer.instance.custom_data)
        rec = serializer.save()
        record(
            AuditLog.Action.UPDATE,
            self.request.user,
            rec,
            {"table": rec.definition.name if rec.definition else "", "from": before, "to": rec.custom_data},
        )

    def perform_destroy(self, instance):
        pk, data = instance.pk, dict(instance.custom_data)
        instance.delete()
        record(
            AuditLog.Action.DELETE,
            self.request.user,
            model="navigation.tablerecord",
            object_id=pk,
            object_repr=f"Record {pk}",
            changes={"before": data},
        )

    @extend_schema(request=dict, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="bulk-archive")
    def bulk_archive(self, request):
        """Archive (or with `restore: true`, un-archive) records."""
        self.check_bulk_permission(request)
        restore = bool((request.data or {}).get("restore"))
        if restore:
            from .table_api import _ids

            ids = _ids((request.data or {}).get("ids"))
        else:
            ids = [r.pk for r in self.bulk_queryset(request)]
        n = TableRecord.objects.filter(pk__in=ids, definition__sidebar_item=self.table_item(), is_archived=restore).update(
            is_archived=not restore
        )
        record(
            AuditLog.Action.BULK_UPDATE,
            request.user,
            model="navigation.tablerecord",
            object_repr=f"{'Restored' if restore else 'Archived'} {n} record(s)",
            changes={"ids": ids},
        )
        return Response({"updated": n})

    @extend_schema(request=dict, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="bulk-move")
    def bulk_move(self, request):
        """Move records to another custom table (values are kept by column key)."""
        self.check_bulk_permission(request)
        target = TableDefinition.objects.filter(pk=(request.data or {}).get("target"), source=CUSTOM).first()
        if target is None or target.sidebar_item_id == self.table_item().pk:
            raise DomainError("Choose another custom table to move the records to.", field="target")
        ids = [r.pk for r in self.bulk_queryset(request)]
        n = TableRecord.objects.filter(pk__in=ids).update(definition=target)
        record(
            AuditLog.Action.BULK_UPDATE,
            request.user,
            model="navigation.tablerecord",
            object_repr=f"Moved {n} record(s) to {target.name}",
            changes={"ids": ids, "target": target.pk},
        )
        return Response({"moved": n, "target": target.name})
