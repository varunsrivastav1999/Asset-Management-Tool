"""Default sidebar. Used by the seed migration and the admin "reset to defaults" action."""

from django.db import transaction

ALL = ["admin", "manager", "employee"]
# Kept literal (not imported from tables.py) so historical migrations stay stable.
ROUTE_TABLES = {
    "/assets": "assets",
    "/receiving": "receipts",
    "/handovers": "handovers",
    "/maintenance": "maintenance",
    "/people/users": "users",
    "/people/departments": "departments",
    "/catalog/locations": "locations",
    "/catalog/vendors": "vendors",
}
STAFF = ["admin", "manager"]
ADMIN = ["admin"]

DEFAULT_SIDEBAR = [
    {
        "name": "Overview",
        "type": "group",
        "roles": ALL,
        "children": [
            {"name": "Dashboard", "route": "/", "icon": "layout-dashboard", "roles": ALL},
            {"name": "Assets", "route": "/assets", "icon": "boxes", "roles": ALL},
            {"name": "Scan", "route": "/scan", "icon": "scan-line", "roles": ALL},
        ],
    },
    {
        "name": "Workflows",
        "type": "group",
        "roles": ALL,
        "children": [
            {"name": "Receiving", "route": "/receiving", "icon": "package-plus", "roles": STAFF},
            {"name": "Handovers", "route": "/handovers", "icon": "arrow-left-right", "roles": ALL},
            {"name": "Maintenance", "route": "/maintenance", "icon": "wrench", "roles": STAFF},
            {"name": "Reminders", "route": "/reminders", "icon": "bell", "roles": STAFF},
        ],
    },
    {
        "name": "Catalog",
        "type": "group",
        "roles": STAFF,
        "children": [
            {"name": "Categories", "route": "/catalog/categories", "icon": "shapes", "roles": STAFF},
            {"name": "Locations", "route": "/catalog/locations", "icon": "map-pin", "roles": STAFF},
            {"name": "Vendors", "route": "/catalog/vendors", "icon": "store", "roles": STAFF},
        ],
    },
    {
        "name": "Organisation",
        "type": "group",
        "roles": STAFF,
        "children": [
            {"name": "People", "route": "/people/users", "icon": "users", "roles": STAFF},
            {"name": "Departments", "route": "/people/departments", "icon": "building-2", "roles": STAFF},
            {"name": "Audit log", "route": "/audit", "icon": "scroll-text", "roles": ADMIN},
        ],
    },
    {
        "name": "Settings",
        "type": "group",
        "roles": ADMIN,
        "children": [
            {"name": "Sidebar", "route": "/settings/sidebar", "icon": "panel-left", "roles": ADMIN},
            {"name": "Dashboard", "route": "/settings/dashboard", "icon": "layout-grid", "roles": ADMIN},
            {"name": "Tables", "route": "/settings/tables", "icon": "list", "roles": ADMIN},
            {"name": "Backups", "route": "/settings/backups", "icon": "hard-drive", "roles": ADMIN},
        ],
    },
]


def seed_sidebar(model, *, replace=False):
    """Create the default sidebar. `model` may be a historical model (migrations) or the real one."""
    with transaction.atomic():
        if replace:
            # Admin-created tables survive a menu reset (moved to the top level); everything else is rebuilt.
            custom = model.objects.filter(definition__source="custom")
            custom.update(parent=None)
            model.objects.exclude(pk__in=custom.values("pk")).delete()
        elif model.objects.exists():
            return 0
        created = 0
        has_table = any(f.name == "table" for f in model._meta.get_fields())
        for gi, group in enumerate(DEFAULT_SIDEBAR):
            parent = model.objects.create(
                name=group["name"], item_type="group", order=gi, visible_roles=group["roles"], icon=group.get("icon", "")
            )
            created += 1
            for ci, child in enumerate(group["children"]):
                extra = {"table": ROUTE_TABLES.get(child["route"], "")} if has_table else {}
                model.objects.create(
                    name=child["name"],
                    item_type="page",
                    route=child["route"],
                    icon=child["icon"],
                    parent=parent,
                    order=ci,
                    visible_roles=child["roles"],
                    **extra,
                )
                created += 1
        if has_table and any(f.name == "definition" for f in model._meta.get_fields()):
            from apps.navigation.definitions import ensure_definition

            Definition = model._meta.get_field("definition").related_model
            for item in model.objects.filter(item_type="page").exclude(table=""):
                ensure_definition(item, Definition)
        return created
