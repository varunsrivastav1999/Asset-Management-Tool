"""Mixin that makes a DRF list endpoint honour a page's TableColumn configuration.

- `?table_item=<sidebar item id>` selects the config (defaults to the table's first page item).
- `?with_columns=1` adds the effective column config to the list payload ("columns with rows").
- `?search=` searches only the configured, searchable columns the user's role may see.
- `?ordering=<key>|-<key>` sorts by any sortable column (built-in expression or custom JSON key).
- `?cf.<key>=<value>` filters on a custom column.
- `GET  …/export-table/?file_format=csv|xlsx` exports exactly the columns the user sees.
- `PATCH …/<id>/custom-data/` edits custom column values (managers/admins).
"""

import csv
import datetime
import decimal
import io

from django.db import transaction
from django.db.models import F, ProtectedError, Q
from django.db.models.expressions import OrderBy
from django.db.models.fields.json import KeyTransform
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import record, snapshot
from apps.core.exceptions import DomainError
from apps.core.permissions import IsManager
from apps.core.roles import effective_role

from .definitions import definition_of, meta
from .models import SidebarItem, TableColumn, TablePreference
from .tables import TABLES, builtin, ensure_columns


def resolve_item(table_key: str, item_id) -> SidebarItem | None:
    qs = SidebarItem.objects.filter(table=table_key, item_type=SidebarItem.Type.PAGE)
    if item_id not in (None, ""):
        try:
            return qs.get(pk=int(item_id))
        except (SidebarItem.DoesNotExist, ValueError, TypeError) as exc:
            raise DomainError("Unknown table page.", field="table_item") from exc
    return qs.order_by("id").first()


def effective_columns(item: SidebarItem | None, table_key: str, user) -> list[dict]:
    """Columns the user's role may see, with per-user effective visibility."""
    role = effective_role(user)
    if item is None:
        # No page configured (e.g. menu item deleted): fall back to registry defaults.
        return [
            {
                "id": None,
                "key": c.key,
                "name": c.name,
                "type": c.type,
                "options": c.options,
                "width": c.width,
                "order": i,
                "is_visible": c.visible,
                "is_required": c.required,
                "is_searchable": bool(c.search),
                "is_sortable": c.sort is not None,
                "is_builtin": True,
                "visible_roles": list(c.roles),
                "visible": c.visible or c.required,
            }
            for i, c in enumerate(TABLES[table_key].columns)
            if role in c.roles
        ]
    ensure_columns(item)
    pref = TablePreference.objects.filter(user=user, sidebar_item=item).first()
    hidden, shown = set(pref.hidden if pref else []), set(pref.shown if pref else [])
    out = []
    for col in item.columns.all():
        if role not in (col.visible_roles or []):
            continue
        visible = col.is_required or (col.key in shown) or (col.is_visible and col.key not in hidden)
        out.append({**ColumnSerializer(col).data, "visible": visible})
    return out


class ColumnSerializer(serializers.ModelSerializer):
    type = serializers.CharField(source="column_type", read_only=True)

    class Meta:
        model = TableColumn
        fields = [
            "id",
            "key",
            "name",
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
        ]


def coerce_value(col: TableColumn, value):
    """Validate a custom column value for storage in custom_data."""
    if value in (None, ""):
        return None
    t = TableColumn.Type
    try:
        if col.column_type == t.NUMBER:
            n = decimal.Decimal(str(value))
            if not n.is_finite():
                raise ValueError
            return int(n) if n == n.to_integral_value() else float(n)
        if col.column_type == t.DATE:
            return datetime.date.fromisoformat(str(value)[:10]).isoformat()
        if col.column_type == t.BOOLEAN:
            if isinstance(value, bool):
                return value
            s = str(value).lower()
            if s in {"true", "1", "yes"}:
                return True
            if s in {"false", "0", "no"}:
                return False
            raise ValueError
        if col.column_type == t.SELECT:
            if col.options and str(value) not in [str(o) for o in col.options]:
                raise ValueError
            return str(value)
        if col.column_type == t.USER:
            if isinstance(value, dict) and "id" in value:
                return {"id": int(value["id"]), "name": str(value.get("name", ""))[:160]}
            raise ValueError
        if col.column_type == t.FILE:
            s = str(value).strip()
            if not s.lower().startswith(("https://", "http://", "/media/")):
                raise ValueError
            return s[:500]
        s = str(value).strip()
        if len(s) > 1000:
            raise ValueError
        return s
    except (ValueError, decimal.InvalidOperation, TypeError) as exc:
        raise DomainError(f"Invalid value for “{col.name}”.", field=col.key) from exc


BULK_LIMIT = 5000


class ConfigurableTableMixin:
    table_key: str = ""
    #: Roles allowed to bulk-delete (checked on top of the view's own permissions).
    bulk_permission_classes = [IsManager]
    #: Past-tense verb reported for bulk deletes (users are deactivated, not deleted).
    bulk_delete_verb = "deleted"

    # --- config ---------------------------------------------------------------
    def table_item(self):
        if not hasattr(self, "_table_item"):
            self._table_item = resolve_item(self.table_key, self.request.query_params.get("table_item"))
        return self._table_item

    def table_columns(self):
        if not hasattr(self, "_table_columns"):
            self._table_columns = effective_columns(self.table_item(), self.table_key, self.request.user)
        return self._table_columns

    def _column_models(self):
        item = self.table_item()
        role = effective_role(self.request.user)
        if not item:
            return []
        ensure_columns(item)
        return [c for c in item.columns.all() if role in (c.visible_roles or [])]

    # --- querying -------------------------------------------------------------
    def column_search_fields(self):
        """ORM paths to search, derived from searchable columns (None = use view defaults)."""
        if self.table_item() is None:
            return None
        paths = []
        for col in self._column_models():
            if not col.is_searchable:
                continue
            if col.is_builtin:
                b = builtin(self.table_key, col.key)
                paths += list(b.search) if b else []
            else:
                paths.append(f"custom_data__{col.key}")
        return list(dict.fromkeys(paths))

    def filter_queryset(self, queryset):
        params = self.request.query_params
        ordering = params.get("ordering")
        queryset = super().filter_queryset(queryset)
        cols = {c.key: c for c in self._column_models()} if self.table_item() else {}
        for name, value in params.items():
            if name.startswith("cf.") and name[3:] in cols and not cols[name[3:]].is_builtin and value != "":
                key = name[3:]
                queryset = queryset.filter(
                    Q(**{f"custom_data__{key}": coerce_value(cols[key], value)}) | Q(**{f"custom_data__{key}__iexact": value})
                )
        if ordering and cols:
            terms = []
            for term in ordering.split(","):
                desc, key = term.startswith("-"), term.lstrip("-")
                col = cols.get(key)
                if not col or not col.is_sortable:
                    continue
                if col.is_builtin:
                    b = builtin(self.table_key, key)
                    expr = b.sort if b else None
                    if expr is None:
                        continue
                    expr = F(expr) if isinstance(expr, str) else expr
                    terms.append(expr.desc(nulls_last=True) if desc else expr.asc(nulls_last=True))
                else:
                    terms.append(OrderBy(KeyTransform(key, "custom_data"), descending=desc, nulls_last=True))
            if terms:
                queryset = queryset.order_by(*terms, "-pk")
        return queryset

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if request.query_params.get("with_columns") in ("1", "true") and isinstance(response.data, dict):
            item = self.table_item()
            response.data["table"] = {
                "key": self.table_key,
                "item": item.pk if item else None,
                "meta": meta(definition_of(item)) if item else None,
                "supports_custom": TABLES[self.table_key].supports_custom,
                "columns": self.table_columns(),
            }
        return response

    # --- inline custom values ---------------------------------------------------
    @action(detail=True, methods=["patch"], url_path="custom-data", permission_classes=[IsManager])
    def custom_data(self, request, pk=None):
        if not TABLES[self.table_key].supports_custom:
            raise DomainError("This table does not support custom columns.")
        obj = self.get_object()
        cols = {c.key: c for c in TableColumn.objects.filter(sidebar_item__table=self.table_key, is_builtin=False)}
        if not isinstance(request.data, dict) or not request.data:
            raise DomainError("Send an object of {column_key: value}.")
        unknown = [k for k in request.data if k not in cols]
        if unknown:
            raise DomainError(f"Unknown custom column(s): {', '.join(unknown)}.")
        data = dict(obj.custom_data or {})
        changes = {}
        for key, raw in request.data.items():
            value = coerce_value(cols[key], raw)
            changes[key] = {"from": data.get(key), "to": value}
            if value is None:
                data.pop(key, None)
            else:
                data[key] = value
        obj.custom_data = data
        obj.save(update_fields=["custom_data", "updated_at"])
        record(AuditLog.Action.UPDATE, request.user, obj, {"custom_data": changes})
        return Response({"id": obj.pk, "custom_data": obj.custom_data})

    # --- bulk -------------------------------------------------------------------
    def check_bulk_permission(self, request):
        for perm in self.bulk_permission_classes:
            if not perm().has_permission(request, self):
                self.permission_denied(request, message=getattr(perm, "message", None))

    def bulk_queryset(self, request):
        """Rows targeted by a bulk action: explicit `ids`, or `all: true` = every row matching the URL's filters."""
        data = request.data if isinstance(request.data, dict) else {}
        if data.get("all") is True:
            qs = self.filter_queryset(self.get_queryset())
        else:
            ids = _ids(data.get("ids"))
            if not ids:
                raise DomainError("Select at least one row.", field="ids")
            qs = self.get_queryset().filter(pk__in=ids)
        objs = list(qs[: BULK_LIMIT + 1])
        if len(objs) > BULK_LIMIT:
            raise DomainError(f"At most {BULK_LIMIT} rows per bulk action — narrow the filters.")
        return objs

    def bulk_delete_reason(self, obj) -> str | None:
        """Why `obj` must be skipped (None = delete it). Override per table."""
        return None

    def bulk_delete_one(self, obj):
        obj.delete()

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        """Atomically delete many rows; rows that can't be deleted are skipped with a reason."""
        self.check_bulk_permission(request)
        objs = self.bulk_queryset(request)
        done, skipped = [], []
        with transaction.atomic():
            for obj in objs:
                label = str(obj)[:120]
                reason = self.bulk_delete_reason(obj)
                if reason:
                    skipped.append({"id": obj.pk, "label": label, "reason": reason})
                    continue
                before, pk, model = snapshot(obj), obj.pk, obj._meta.label_lower
                sid = transaction.savepoint()
                try:
                    self.bulk_delete_one(obj)
                except ProtectedError:
                    transaction.savepoint_rollback(sid)
                    skipped.append({"id": pk, "label": label, "reason": "Referenced by other records."})
                    continue
                transaction.savepoint_commit(sid)
                done.append(pk)
                record(
                    AuditLog.Action.DELETE,
                    request.user,
                    model=model,
                    object_id=pk,
                    object_repr=label,
                    changes={"before": before, "bulk": True},
                )
        record(
            AuditLog.Action.BULK_UPDATE,
            request.user,
            model=self.table_key,
            object_repr=f"Bulk {self.bulk_delete_verb} {len(done)}, skipped {len(skipped)}",
            changes={"ids": done, "skipped": [s["id"] for s in skipped]},
        )
        return Response({"deleted": len(done), "deleted_ids": done, "skipped": skipped, "verb": self.bulk_delete_verb})

    # --- export -----------------------------------------------------------------
    @action(detail=False, methods=["get"], url_path="export-table", permission_classes=[IsManager])
    def export_table(self, request):
        cols = [c for c in self.table_columns() if c["visible"]]
        scope = request.query_params.get("scope", "filtered")
        if scope == "selected":
            ids = _ids(request.query_params.get("ids", ""))
            if not ids:
                raise DomainError("Select at least one row to export.", field="ids")
            qs = self.get_queryset().filter(pk__in=ids)
        elif scope == "all":
            qs = self.get_queryset()
        else:
            qs = self.filter_queryset(self.get_queryset())
        fmt = request.query_params.get("file_format", "xlsx")
        content, content_type, ext = build_export(self.table_key, cols, qs[:20000], fmt)
        record(
            AuditLog.Action.EXPORT,
            request.user,
            model=self.table_key,
            object_repr=f"{content.count(b'\n') if ext == 'csv' else qs.count()} rows ({fmt}, {scope})",
            changes={"columns": [c["name"] for c in cols]},
        )
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        return _file(content, content_type, f"{self.table_key}-{stamp}.{ext}")


def export_rows(table_key: str, cols: list[dict], objects) -> tuple[list[str], list[list]]:
    """Header (configured column names) and formula-safe cell values for the given objects."""
    rows = []
    for i, obj in enumerate(objects, start=1):
        row = []
        for c in cols:
            if c["type"] == "auto_number":
                row.append(i)
            elif c["is_builtin"]:
                b = builtin(table_key, c["key"])
                row.append(_cell(b.get(obj) if b and b.get else ""))
            else:
                v = (getattr(obj, "custom_data", None) or {}).get(c["key"], "")
                row.append(_cell(v.get("name") if isinstance(v, dict) else v))
        rows.append(row)
    return [c["name"] for c in cols], rows


def build_export(table_key: str, cols: list[dict], objects, fmt: str = "xlsx") -> tuple[bytes, str, str]:
    """Render rows as CSV (UTF-8 BOM), XLSX or PDF. Returns (content, content_type, extension)."""
    header, rows = export_rows(table_key, cols, objects)
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        w.writerows(rows)
        return ("\ufeff" + buf.getvalue()).encode(), "text/csv; charset=utf-8", "csv"
    if fmt == "pdf":
        from apps.core.pdf import table_pdf

        return table_pdf(TABLES[table_key].label, header, rows), "application/pdf", "pdf"
    wb = Workbook()
    ws = wb.active
    ws.title = TABLES[table_key].label[:30]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="064E3B")
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"


def _ids(raw) -> list[int]:
    if isinstance(raw, str):
        raw = [p for p in raw.split(",") if p.strip()]
    try:
        return [int(i) for i in raw or []]
    except (TypeError, ValueError) as exc:
        raise DomainError("ids must be a list of integers.", field="ids") from exc


def _cell(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        value = value.isoformat()
    if isinstance(value, decimal.Decimal):
        value = float(value)
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value  # spreadsheet formula injection guard
    return value


def _file(content, content_type, filename):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response
