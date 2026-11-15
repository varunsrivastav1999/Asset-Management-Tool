"""Default dashboard layout (seed migration + admin "reset to defaults")."""

from django.db import transaction

ALL = ["admin", "manager", "employee"]
STAFF = ["admin", "manager"]

DEFAULT_WIDGETS = [
    ("My assets", "stat", "my_assets", "", "sm", ALL, {"tone": "violet", "icon": "boxes"}),
    ("Awaiting my signature", "stat", "awaiting_signature", "", "sm", ALL, {"tone": "amber", "icon": "pen-line"}),
    ("Value in my care", "stat", "my_assets_value", "", "sm", ["employee"], {"tone": "emerald", "icon": "circle-dollar-sign"}),
    ("My warranties ending", "stat", "my_warranty_expiring", "", "sm", ["employee"], {"tone": "rose", "icon": "shield-alert"}),
    ("Pending handovers", "stat", "pending_handovers", "", "sm", STAFF, {"tone": "amber", "icon": "arrow-left-right"}),
    ("Open maintenance", "stat", "open_maintenance", "", "sm", STAFF, {"tone": "rose", "icon": "wrench"}),
    ("Total assets", "stat", "total_assets", "", "sm", STAFF, {"tone": "accent", "icon": "boxes"}),
    ("Portfolio value", "stat", "portfolio_value", "", "sm", STAFF, {"tone": "emerald", "icon": "circle-dollar-sign"}),
    ("Utilisation", "stat", "utilization", "", "sm", STAFF, {"tone": "violet", "icon": "gauge"}),
    ("Warranties ending ≤ 30d", "stat", "warranty_expiring", "", "sm", STAFF, {"tone": "rose", "icon": "shield-alert"}),
    ("Activity", "chart", "activity_timeline", "line", "lg", STAFF, {}),
    ("Status breakdown", "chart", "status_breakdown", "doughnut", "sm", STAFF, {}),
    ("By category", "chart", "assets_by_category", "hbar", "md", STAFF, {}),
    ("By department", "chart", "assets_by_department", "bar", "md", STAFF, {}),
    ("Recent activity", "table", "recent_activity", "", "lg", STAFF, {}),
    ("Warranties ending soon", "table", "expiring_warranties", "", "sm", STAFF, {}),
    ("My assets", "chart", "my_status_breakdown", "doughnut", "md", ["employee"], {}),
    ("Assets in my care", "table", "my_assets_list", "", "md", ["employee"], {}),
]


def seed_widgets(model, *, replace=False):
    with transaction.atomic():
        if replace:
            model.objects.all().delete()
        elif model.objects.exists():
            return 0
        model.objects.bulk_create(
            [
                model(
                    title=t,
                    widget_type=wt,
                    data_source=src,
                    chart_type=ct,
                    size=size,
                    position=i,
                    visible_roles=roles,
                    config=cfg,
                )
                for i, (t, wt, src, ct, size, roles, cfg) in enumerate(DEFAULT_WIDGETS)
            ]
        )
        return len(DEFAULT_WIDGETS)
