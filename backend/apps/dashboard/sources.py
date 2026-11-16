"""Registry of dashboard data sources.

Each source declares which widget types it can feed and the minimum role allowed to see it.
Organisation-wide sources are manager+ only; that rule is enforced when widgets are saved
(visible_roles validation) *and* when data is served (defence in depth).
"""

from apps.assets.models import Asset

from . import table_sources
from .views import CACHE_KEY, CACHE_TTL, compute_stats, personal_stats

STAT, CHART, TABLE = "stat", "chart", "table"
ORG, PERSONAL = "org", "personal"

STATUS_LABELS = dict(Asset.Status.choices)
STATUS_COLORS = {"in_stock": "#10b981", "assigned": "#a78bfa", "in_repair": "#fbbf24", "retired": "#94a3b8", "lost": "#fb7185"}

SOURCES = {
    # --- organisation-wide (manager / admin) ---
    "total_assets": {"label": "Total assets", "types": [STAT], "scope": ORG},
    "portfolio_value": {"label": "Portfolio value", "types": [STAT], "scope": ORG},
    "utilization": {"label": "Utilisation", "types": [STAT], "scope": ORG},
    "open_maintenance": {"label": "Open maintenance", "types": [STAT], "scope": ORG},
    "pending_handovers": {"label": "Pending handovers", "types": [STAT], "scope": ORG},
    "warranty_expiring": {"label": "Warranties ending ≤ 30 days", "types": [STAT], "scope": ORG},
    "status_breakdown": {"label": "Assets by status", "types": [CHART], "charts": ["doughnut", "bar"], "scope": ORG},
    "activity_timeline": {"label": "Activity (12 months)", "types": [CHART], "charts": ["line", "bar"], "scope": ORG},
    "assets_by_category": {"label": "Assets by category", "types": [CHART], "charts": ["hbar", "bar", "doughnut"], "scope": ORG},
    "assets_by_department": {
        "label": "Assets by department",
        "types": [CHART],
        "charts": ["bar", "hbar", "doughnut"],
        "scope": ORG,
    },
    "recent_activity": {"label": "Recent activity", "types": [TABLE], "scope": ORG},
    "expiring_warranties": {"label": "Warranties ending soon", "types": [TABLE], "scope": ORG},
    "maintenance_due": {"label": "Maintenance due", "types": [TABLE], "scope": ORG},
    # --- personal (any role) ---
    "my_assets": {"label": "My assets", "types": [STAT], "scope": PERSONAL},
    "awaiting_signature": {"label": "Awaiting my signature", "types": [STAT], "scope": PERSONAL},
    "my_assets_value": {"label": "Value in my care", "types": [STAT], "scope": PERSONAL},
    "my_warranty_expiring": {"label": "My warranties ending soon", "types": [STAT], "scope": PERSONAL},
    "my_status_breakdown": {"label": "My assets by status", "types": [CHART], "charts": ["doughnut", "bar"], "scope": PERSONAL},
    "my_assets_list": {"label": "My assets (list)", "types": [TABLE], "scope": PERSONAL},
}

CHART_TYPES = ["doughnut", "bar", "hbar", "line"]


def source_choices():
    return [(k, v["label"]) for k, v in SOURCES.items()]


def source_meta(source: str) -> dict | None:
    """Catalog entry for any source: the fixed ones above, or one built from a custom table (table:<id>:...)."""
    return SOURCES.get(source) or table_sources.meta(source)


def allowed_roles(source: str) -> list[str]:
    meta = source_meta(source)
    if meta is None:
        return []
    if meta["scope"] == "table":  # whoever can see the table's page
        return (
            [r for r in ("admin", "manager", "employee") if r == "admin" or r in meta["roles"]] if meta["active"] else ["admin"]
        )
    return ["admin", "manager"] if meta["scope"] == ORG else ["admin", "manager", "employee"]


def catalog():
    fixed = [
        {
            "key": k,
            "label": v["label"],
            "group": "Assets & workflows",
            "types": v["types"],
            "charts": v.get("charts", []),
            "scope": v["scope"],
            "allowed_roles": allowed_roles(k),
        }
        for k, v in SOURCES.items()
    ]
    tables = [
        {
            "key": t["key"],
            "label": t["label"],
            "group": f"Table: {t['group']}",
            "types": t["types"],
            "charts": t.get("charts", []),
            "scope": "table",
            "allowed_roles": allowed_roles(t["key"]),
        }
        for t in table_sources.catalog()
    ]
    return fixed + tables


class DataContext:
    """Lazily computes and memoises the shared payloads a request's widgets need."""

    def __init__(self, user):
        self.user = user
        self._org = None
        self._personal = None

    @property
    def org(self):
        if self._org is None:
            from django.core.cache import cache

            data = cache.get(CACHE_KEY)
            if data is None:
                data = compute_stats()
                cache.set(CACHE_KEY, data, CACHE_TTL)
            self._org = data
        return self._org

    @property
    def personal(self):
        if self._personal is None:
            self._personal = personal_stats(self.user)
        return self._personal


def _stat(value, fmt="number", hint="", link=""):
    return {"value": value, "format": fmt, "hint": hint, "link": link}


def _chart(labels, datasets):
    return {"labels": labels, "datasets": datasets}


def _table(columns, rows):
    return {"columns": columns, "rows": rows}


def _status_chart(by_status: dict, keys: list[str]):
    return _chart(
        [STATUS_LABELS[k] for k in keys],
        [{"label": "Assets", "data": [by_status.get(k, 0) for k in keys], "colors": [STATUS_COLORS[k] for k in keys]}],
    )


def _dated_assets_table(assets: list, date_key: str, date_label: str):
    rows = [{"asset": f"{a['asset_tag']} · {a['name']}", "date": a[date_key], "link": f"/assets/{a['id']}"} for a in assets]
    return _table([{"key": "asset", "label": "Asset"}, {"key": "date", "label": date_label, "type": "date"}], rows)


# --- organisation-wide sources ---------------------------------------------------------------
def _total_assets(ctx):
    t = ctx.org["totals"]
    return _stat(t["assets"], hint=f"{t['active']} active", link="/assets")


def _warranty_expiring(ctx):
    w = ctx.org["warranty"]
    return _stat(w["d30"], hint=f"{w['expired']} already expired", link="/assets?warranty_expiring_in=30")


def _activity_timeline(ctx):
    tl = ctx.org["timeline"]
    series = (("Issued", "issued", "#a78bfa"), ("Returned", "returned", "#34d399"), ("Added", "added", "#10b981"))
    return _chart(
        [t["month"] for t in tl], [{"label": label, "data": [t[key] for t in tl], "color": color} for label, key, color in series]
    )


def _assets_by_category(ctx):
    rows = ctx.org["by_category"]
    return _chart(
        [r["name"] for r in rows],
        [{"label": "Assets", "data": [r["count"] for r in rows], "colors": [r["color"] or "#10b981" for r in rows]}],
    )


def _assets_by_department(ctx):
    rows = ctx.org["by_department"]
    return _chart([r["name"] for r in rows], [{"label": "Assets", "data": [r["count"] for r in rows], "color": "#a78bfa"}])


def _recent_activity(ctx):
    rows = [
        {
            "label": e["label"],
            "event_type": e["event_type"],
            "asset": f"{e['asset_tag']} · {e['asset_name']}",
            "actor": e["actor_name"],
            "when": e["created_at"],
            "link": f"/assets/{e['asset_id']}",
        }
        for e in ctx.org["recent_activity"]
    ]
    columns = [
        {"key": "label", "label": "Event", "type": "badge"},
        {"key": "asset", "label": "Asset"},
        {"key": "actor", "label": "By"},
        {"key": "when", "label": "When", "type": "ago"},
    ]
    return _table(columns, rows)


# --- personal sources ------------------------------------------------------------------------
def _my_status_breakdown(ctx):
    by_status = ctx.personal["my_by_status"]
    return _status_chart(by_status, [k for k in STATUS_LABELS if by_status.get(k)])


def _my_assets_list(ctx):
    qs = (
        Asset.objects.filter(assigned_to=ctx.user)
        .exclude(status=Asset.Status.RETIRED)
        .select_related("category")
        .order_by("-assigned_at")[:8]
    )
    rows = [
        {"asset": f"{a.asset_tag} · {a.name}", "category": a.category.name, "status": a.status, "link": f"/assets/{a.pk}"}
        for a in qs
    ]
    columns = [
        {"key": "asset", "label": "Asset"},
        {"key": "category", "label": "Category"},
        {"key": "status", "label": "Status", "type": "status"},
    ]
    return _table(columns, rows)


# Data source key -> builder(ctx). Add a widget data source by adding one entry (open/closed).
RESOLVERS = {
    "total_assets": _total_assets,
    "portfolio_value": lambda ctx: _stat(ctx.org["totals"]["value"], "currency", "Active assets at cost"),
    "utilization": lambda ctx: _stat(ctx.org["totals"]["utilization"], "percent", "Assigned vs. usable"),
    "open_maintenance": lambda ctx: _stat(ctx.org["totals"]["open_maintenance"], link="/maintenance"),
    "pending_handovers": lambda ctx: _stat(ctx.org["totals"]["pending_handovers"], link="/handovers?status=pending"),
    "warranty_expiring": _warranty_expiring,
    "status_breakdown": lambda ctx: _status_chart(ctx.org["by_status"], list(STATUS_LABELS)),
    "activity_timeline": _activity_timeline,
    "assets_by_category": _assets_by_category,
    "assets_by_department": _assets_by_department,
    "recent_activity": _recent_activity,
    "expiring_warranties": lambda ctx: _dated_assets_table(ctx.org["expiring_soon"], "warranty_expiry", "Expires"),
    "maintenance_due": lambda ctx: _dated_assets_table(ctx.org["maintenance_due"], "next_maintenance_date", "Due"),
    "my_assets": lambda ctx: _stat(ctx.personal["my_assets"], link="/assets"),
    "awaiting_signature": lambda ctx: _stat(ctx.personal["awaiting_signature"], link="/handovers?awaiting_me=1"),
    "my_assets_value": lambda ctx: _stat(ctx.personal["my_value"], "currency"),
    "my_warranty_expiring": lambda ctx: _stat(ctx.personal["my_warranty_expiring"]),
    "my_status_breakdown": _my_status_breakdown,
    "my_assets_list": _my_assets_list,
}


def resolve(source: str, ctx: DataContext):
    """Widget payload for a data source, or None for an unknown key."""
    builder = RESOLVERS.get(source)
    if builder:
        return builder(ctx)
    return table_sources.resolve(source, ctx)
