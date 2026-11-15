"""Registry of dashboard data sources.

Each source declares which widget types it can feed and the minimum role allowed to see it.
Organisation-wide sources are manager+ only; that rule is enforced when widgets are saved
(visible_roles validation) *and* when data is served (defence in depth).
"""

from apps.assets.models import Asset

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


def allowed_roles(source: str) -> list[str]:
    return ["admin", "manager"] if SOURCES[source]["scope"] == ORG else ["admin", "manager", "employee"]


def catalog():
    return [
        {
            "key": k,
            "label": v["label"],
            "types": v["types"],
            "charts": v.get("charts", []),
            "scope": v["scope"],
            "allowed_roles": allowed_roles(k),
        }
        for k, v in SOURCES.items()
    ]


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


def resolve(source: str, ctx: DataContext):
    o = lambda: ctx.org  # noqa: E731
    p = lambda: ctx.personal  # noqa: E731
    if source == "total_assets":
        t = o()["totals"]
        return _stat(t["assets"], hint=f"{t['active']} active", link="/assets")
    if source == "portfolio_value":
        return _stat(o()["totals"]["value"], "currency", "Active assets at cost")
    if source == "utilization":
        return _stat(o()["totals"]["utilization"], "percent", "Assigned vs. usable")
    if source == "open_maintenance":
        return _stat(o()["totals"]["open_maintenance"], link="/maintenance")
    if source == "pending_handovers":
        return _stat(o()["totals"]["pending_handovers"], link="/handovers?status=pending")
    if source == "warranty_expiring":
        w = o()["warranty"]
        return _stat(w["d30"], hint=f"{w['expired']} already expired", link="/assets?warranty_expiring_in=30")
    if source == "status_breakdown":
        s = o()["by_status"]
        keys = list(STATUS_LABELS)
        return _chart(
            [STATUS_LABELS[k] for k in keys],
            [{"label": "Assets", "data": [s.get(k, 0) for k in keys], "colors": [STATUS_COLORS[k] for k in keys]}],
        )
    if source == "activity_timeline":
        tl = o()["timeline"]
        return _chart(
            [t["month"] for t in tl],
            [
                {"label": "Issued", "data": [t["issued"] for t in tl], "color": "#a78bfa"},
                {"label": "Returned", "data": [t["returned"] for t in tl], "color": "#34d399"},
                {"label": "Added", "data": [t["added"] for t in tl], "color": "#10b981"},
            ],
        )
    if source == "assets_by_category":
        rows = o()["by_category"]
        return _chart(
            [r["name"] for r in rows],
            [{"label": "Assets", "data": [r["count"] for r in rows], "colors": [r["color"] or "#10b981" for r in rows]}],
        )
    if source == "assets_by_department":
        rows = o()["by_department"]
        return _chart([r["name"] for r in rows], [{"label": "Assets", "data": [r["count"] for r in rows], "color": "#a78bfa"}])
    if source == "recent_activity":
        rows = [
            {
                "label": e["label"],
                "event_type": e["event_type"],
                "asset": f"{e['asset_tag']} · {e['asset_name']}",
                "actor": e["actor_name"],
                "when": e["created_at"],
                "link": f"/assets/{e['asset_id']}",
            }
            for e in o()["recent_activity"]
        ]
        return _table(
            [
                {"key": "label", "label": "Event", "type": "badge"},
                {"key": "asset", "label": "Asset"},
                {"key": "actor", "label": "By"},
                {"key": "when", "label": "When", "type": "ago"},
            ],
            rows,
        )
    if source == "expiring_warranties":
        rows = [
            {"asset": f"{a['asset_tag']} · {a['name']}", "date": a["warranty_expiry"], "link": f"/assets/{a['id']}"}
            for a in o()["expiring_soon"]
        ]
        return _table([{"key": "asset", "label": "Asset"}, {"key": "date", "label": "Expires", "type": "date"}], rows)
    if source == "maintenance_due":
        rows = [
            {"asset": f"{a['asset_tag']} · {a['name']}", "date": a["next_maintenance_date"], "link": f"/assets/{a['id']}"}
            for a in o()["maintenance_due"]
        ]
        return _table([{"key": "asset", "label": "Asset"}, {"key": "date", "label": "Due", "type": "date"}], rows)
    if source == "my_assets":
        return _stat(p()["my_assets"], link="/assets")
    if source == "awaiting_signature":
        return _stat(p()["awaiting_signature"], link="/handovers?awaiting_me=1")
    if source == "my_assets_value":
        return _stat(p()["my_value"], "currency")
    if source == "my_warranty_expiring":
        return _stat(p()["my_warranty_expiring"])
    if source == "my_status_breakdown":
        s = p()["my_by_status"]
        keys = [k for k in STATUS_LABELS if s.get(k)]
        return _chart(
            [STATUS_LABELS[k] for k in keys],
            [{"label": "Assets", "data": [s[k] for k in keys], "colors": [STATUS_COLORS[k] for k in keys]}],
        )
    if source == "my_assets_list":
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
        return _table(
            [
                {"key": "asset", "label": "Asset"},
                {"key": "category", "label": "Category"},
                {"key": "status", "label": "Status", "type": "status"},
            ],
            rows,
        )
    return None
