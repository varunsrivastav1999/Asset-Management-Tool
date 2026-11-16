"""Dashboard data sources built from admin-created (custom) tables.

Keys are dynamic, so widgets keep working as tables are added:
    table:<definition id>:count            stat   live rows, with how many were added in the last 30 days
    table:<definition id>:by:<column key>  chart  rows grouped by a Select / Status / Yes-No / Person column
    table:<definition id>:latest           table  the newest rows

A table widget may only be shown to roles that can see the table's page; that is checked when the widget is saved
and again whenever data is served, and a widget whose table (or column) is gone resolves to "unknown source".
"""

import datetime
from collections import Counter

from django.utils import timezone

from apps.navigation.models import TableColumn, TableDefinition, TableRecord, title_keys

STAT, CHART, TABLE = "stat", "chart", "table"
GROUPABLE = {TableColumn.Type.SELECT, TableColumn.Type.STATUS, TableColumn.Type.BOOLEAN, TableColumn.Type.USER}
PALETTE = ["#10b981", "#a78bfa", "#fbbf24", "#38bdf8", "#fb7185", "#34d399", "#f472b6", "#94a3b8"]
MAX_GROUPS = 12


def _parse(key: str):
    """'table:7:by:state' -> (7, 'by', 'state'); None for anything else."""
    parts = (key or "").split(":")
    if len(parts) < 3 or parts[0] != "table" or not parts[1].isdigit():
        return None
    kind = parts[2]
    if kind in ("count", "latest") and len(parts) == 3:
        return int(parts[1]), kind, None
    if kind == "by" and len(parts) == 4 and parts[3]:
        return int(parts[1]), kind, parts[3]
    return None


def _definition(defn_id: int):
    return TableDefinition.objects.select_related("sidebar_item").filter(pk=defn_id, source=TableDefinition.CUSTOM).first()


def _group_column(defn, key):
    return TableColumn.objects.filter(
        sidebar_item=defn.sidebar_item, key=key, is_builtin=False, column_type__in=GROUPABLE
    ).first()


def meta(key: str) -> dict | None:
    """Catalog entry for a table source key, or None if it doesn't (or no longer does) exist."""
    parsed = _parse(key)
    if parsed is None:
        return None
    defn_id, kind, col_key = parsed
    defn = _definition(defn_id)
    if defn is None:
        return None
    roles = list(defn.sidebar_item.visible_roles or [])
    base = {"group": defn.name, "scope": "table", "roles": roles, "active": defn.sidebar_item.is_active}
    if kind == "count":
        return {**base, "label": f"{defn.name}: number of rows", "types": [STAT]}
    if kind == "latest":
        return {**base, "label": f"{defn.name}: latest rows", "types": [TABLE]}
    col = _group_column(defn, col_key)
    if col is None:
        return None
    return {**base, "label": f"{defn.name} by {col.name}", "types": [CHART], "charts": ["doughnut", "bar", "hbar"]}


def catalog() -> list[dict]:
    """Every source the current custom tables offer, for the widget editor."""
    out = []
    defs = TableDefinition.objects.filter(source=TableDefinition.CUSTOM).select_related("sidebar_item").order_by("name")
    groupable = {}
    for col in TableColumn.objects.filter(
        sidebar_item__definition__source=TableDefinition.CUSTOM, is_builtin=False, column_type__in=GROUPABLE
    ).order_by("order"):
        groupable.setdefault(col.sidebar_item_id, []).append(col)
    for defn in defs:
        keys = [f"table:{defn.pk}:count", *(f"table:{defn.pk}:by:{c.key}" for c in groupable.get(defn.sidebar_item_id, []))]
        keys.append(f"table:{defn.pk}:latest")
        for key in keys:
            m = meta(key)
            if m:
                out.append({"key": key, **m})
    return out


def _rows(defn):
    return TableRecord.objects.filter(definition=defn, is_archived=False)


def _label(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if isinstance(value, dict):
        return str(value.get("name") or value.get("id") or "—")
    return str(value) if value not in (None, "") else "Not set"


def resolve(key: str, ctx) -> dict | None:
    parsed = _parse(key)
    defn = _definition(parsed[0]) if parsed else None
    if defn is None:
        return None
    _, kind, col_key = parsed
    route = defn.sidebar_item.route
    if kind == "count":
        rows = _rows(defn)
        recent = rows.filter(created_at__gte=timezone.now() - datetime.timedelta(days=30)).count()
        return {"value": rows.count(), "format": "number", "hint": f"{recent} added in 30 days", "link": route}
    if kind == "latest":
        items = list(_rows(defn).order_by("-created_at", "-id")[:8])
        keys = title_keys(defn)
        return {
            "columns": [
                {"key": "title", "label": defn.singular or "Row"},
                {"key": "code", "label": "Code"},
                {"key": "when", "label": "Added", "type": "ago"},
            ],
            "rows": [
                {"title": r.title_from(keys), "code": r.code, "when": r.created_at.isoformat(), "link": f"{route}?open={r.code}"}
                for r in items
            ],
        }
    col = _group_column(defn, col_key)
    if col is None:
        return None
    counts = Counter(_label((r or {}).get(col_key)) for r in _rows(defn).values_list("custom_data", flat=True))
    ordered = [o for o in (col.options if isinstance(col.options, list) else []) if o in counts]
    ordered += [k for k, _ in counts.most_common() if k not in ordered]
    labels = ordered[:MAX_GROUPS]
    return {
        "labels": labels,
        "datasets": [
            {
                "label": defn.name,
                "data": [counts[k] for k in labels],
                "colors": [PALETTE[i % len(PALETTE)] for i in range(len(labels))],
            }
        ],
    }
