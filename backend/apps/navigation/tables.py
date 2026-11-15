"""Table definitions for configurable, sidebar-page-scoped data tables.

Each table lists its *built-in* columns: the row key the frontend reads, a default label and type,
which ORM paths it searches, how it sorts, and how it exports. Admins can rename, hide, reorder
and role-restrict built-ins, and add *custom* columns whose values live in the model's
`custom_data` JSONB (no schema migration per column).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from django.db.models import F
from django.db.models.functions import Coalesce

ALL = ["admin", "manager", "employee"]
STAFF = ["admin", "manager"]


@dataclass(frozen=True)
class Builtin:
    key: str
    name: str
    type: str = "text"
    visible: bool = True
    required: bool = False
    search: tuple[str, ...] = ()
    sort: Any = None  # ORM path or expression; None = not sortable
    get: Callable | None = None  # export value getter(obj)
    options: Any = field(default_factory=list)
    width: int | None = None
    roles: tuple[str, ...] = tuple(ALL)


@dataclass(frozen=True)
class TableDef:
    key: str
    label: str
    route: str
    supports_custom: bool
    columns: tuple[Builtin, ...]


def _name(user):
    return (user.get_full_name() or user.email) if user else ""


def _date(d):
    return d.isoformat() if d else ""


SNO = Builtin("sno", "S.No", "auto_number", required=True, width=64)

TABLES: dict[str, TableDef] = {
    "assets": TableDef(
        "assets",
        "Assets",
        "/assets",
        True,
        (
            SNO,
            Builtin(
                "name",
                "Item",
                required=True,
                search=("name", "asset_tag", "serial_number", "model", "manufacturer"),
                sort="name",
                get=lambda a: a.name,
            ),
            Builtin("asset_tag", "Tag", visible=False, search=("asset_tag",), sort="asset_tag", get=lambda a: a.asset_tag),
            Builtin(
                "category.name",
                "Category",
                visible=False,
                search=("category__name",),
                sort="category__name",
                get=lambda a: a.category.name,
            ),
            Builtin(
                "received_date",
                "Received",
                "date",
                sort=Coalesce(F("receipt__received_date"), F("purchase_date")),
                get=lambda a: _date(a.receipt.received_date if a.receipt else a.purchase_date),
            ),
            Builtin("status", "Status", "status", sort="status", get=lambda a: a.get_status_display(), options={"kind": "asset"}),
            Builtin(
                "assigned_to",
                "Assigned To",
                "user",
                search=("assigned_to__first_name", "assigned_to__last_name", "assigned_to__email", "department__name"),
                sort="assigned_to__first_name",
                get=lambda a: _name(a.assigned_to) or (a.department.name if a.department else ""),
            ),
            Builtin(
                "serial_number",
                "Serial",
                visible=False,
                search=("serial_number",),
                sort="serial_number",
                get=lambda a: a.serial_number or "",
            ),
            Builtin(
                "location_name",
                "Location",
                visible=False,
                search=("location__name",),
                sort="location__name",
                get=lambda a: a.location.name if a.location else "",
            ),
            Builtin(
                "condition",
                "Condition",
                "select",
                visible=False,
                sort="condition",
                get=lambda a: a.get_condition_display(),
                options=["new", "good", "fair", "poor", "damaged"],
            ),
            Builtin("warranty_expiry", "Warranty", "date", sort="warranty_expiry", get=lambda a: _date(a.warranty_expiry)),
            Builtin(
                "purchase_cost",
                "Cost",
                "number",
                visible=False,
                sort="purchase_cost",
                get=lambda a: a.purchase_cost if a.purchase_cost is not None else "",
                roles=tuple(STAFF),
                options={"format": "currency"},
            ),
            Builtin("updated_at", "Updated", "date", visible=False, sort="updated_at", get=lambda a: a.updated_at.isoformat()),
        ),
    ),
    "receipts": TableDef(
        "receipts",
        "Receiving",
        "/receiving",
        True,
        (
            SNO,
            Builtin(
                "reference",
                "Reference",
                required=True,
                search=("reference", "invoice_number", "po_number"),
                sort="reference",
                get=lambda r: r.reference,
            ),
            Builtin(
                "vendor_name",
                "Vendor",
                search=("vendor__name",),
                sort="vendor__name",
                get=lambda r: r.vendor.name if r.vendor else "",
            ),
            Builtin("received_date", "Received", "date", sort="received_date", get=lambda r: _date(r.received_date)),
            Builtin(
                "received_by_name",
                "Received by",
                "user",
                visible=False,
                search=("received_by__first_name", "received_by__last_name"),
                get=lambda r: _name(r.received_by),
            ),
            Builtin("asset_count", "Items", "number", sort="asset_count", get=lambda r: getattr(r, "asset_count", "")),
            Builtin(
                "total_value",
                "Value",
                "number",
                sort="total_value",
                get=lambda r: getattr(r, "total_value", "") or "",
                options={"format": "currency"},
            ),
            Builtin("is_signed", "Signed", "boolean", visible=False, get=lambda r: bool(r.signature)),
            Builtin(
                "invoice_number",
                "Invoice #",
                visible=False,
                search=("invoice_number",),
                sort="invoice_number",
                get=lambda r: r.invoice_number,
            ),
            Builtin("po_number", "PO #", visible=False, search=("po_number",), sort="po_number", get=lambda r: r.po_number),
        ),
    ),
    "handovers": TableDef(
        "handovers",
        "Handovers",
        "/handovers",
        True,
        (
            SNO,
            Builtin(
                "reference",
                "Reference",
                required=True,
                search=("reference", "items__asset__asset_tag"),
                sort="reference",
                get=lambda h: h.reference,
            ),
            Builtin(
                "type_display",
                "Type",
                "select",
                sort="type",
                get=lambda h: h.get_type_display(),
                options=["Issue", "Return", "Transfer"],
            ),
            Builtin(
                "from_name",
                "From",
                "user",
                search=("from_user__first_name", "from_user__last_name", "from_user__email"),
                get=lambda h: _name(h.from_user) or (h.from_department.name if h.from_department else "Store"),
            ),
            Builtin(
                "to_name",
                "To",
                "user",
                search=("to_user__first_name", "to_user__last_name", "to_user__email"),
                get=lambda h: _name(h.to_user) or (h.to_department.name if h.to_department else "Store"),
            ),
            Builtin("item_count", "Assets", "number", sort="item_count", get=lambda h: getattr(h, "item_count", "")),
            Builtin(
                "status", "Status", "status", sort="status", get=lambda h: h.get_status_display(), options={"kind": "handover"}
            ),
            Builtin("signer_name", "Signer", "user", visible=False, get=lambda h: _name(h.signer)),
            Builtin("created_at", "Created", "date", sort="created_at", get=lambda h: h.created_at.isoformat()),
            Builtin(
                "expected_return_date",
                "Return by",
                "date",
                visible=False,
                sort="expected_return_date",
                get=lambda h: _date(h.expected_return_date),
            ),
        ),
    ),
    "maintenance": TableDef(
        "maintenance",
        "Maintenance",
        "/maintenance",
        True,
        (
            SNO,
            Builtin(
                "title", "Work", required=True, search=("title", "description", "technician"), sort="title", get=lambda m: m.title
            ),
            Builtin(
                "asset_tag",
                "Asset",
                search=("asset__asset_tag", "asset__name"),
                sort="asset__asset_tag",
                get=lambda m: f"{m.asset.asset_tag} {m.asset.name}",
            ),
            Builtin(
                "kind_display",
                "Type",
                "select",
                visible=False,
                sort="kind",
                get=lambda m: m.get_kind_display(),
                options=["Preventive", "Repair", "Inspection", "Calibration"],
            ),
            Builtin("scheduled_date", "Scheduled", "date", sort="scheduled_date", get=lambda m: _date(m.scheduled_date)),
            Builtin(
                "status", "Status", "status", sort="status", get=lambda m: m.get_status_display(), options={"kind": "maintenance"}
            ),
            Builtin(
                "cost",
                "Cost",
                "number",
                sort="cost",
                get=lambda m: m.cost if m.cost is not None else "",
                options={"format": "currency"},
            ),
            Builtin(
                "technician", "Technician", visible=False, search=("technician",), sort="technician", get=lambda m: m.technician
            ),
            Builtin(
                "completed_date", "Completed", "date", visible=False, sort="completed_date", get=lambda m: _date(m.completed_date)
            ),
        ),
    ),
    "users": TableDef(
        "users",
        "People",
        "/people/users",
        False,
        (
            SNO,
            Builtin(
                "full_name",
                "Person",
                "user",
                required=True,
                search=("first_name", "last_name", "email", "employee_id"),
                sort="first_name",
                get=lambda u: _name(u),
            ),
            Builtin("email", "Email", visible=False, search=("email",), sort="email", get=lambda u: u.email),
            Builtin(
                "employee_id",
                "Employee ID",
                visible=False,
                search=("employee_id",),
                sort="employee_id",
                get=lambda u: u.employee_id or "",
            ),
            Builtin("role", "Role", "select", sort="role", get=lambda u: u.role, options=["admin", "manager", "employee"]),
            Builtin(
                "department_name",
                "Department",
                search=("department__name",),
                sort="department__name",
                get=lambda u: u.department.name if u.department else "",
            ),
            Builtin("job_title", "Job title", visible=False, search=("job_title",), sort="job_title", get=lambda u: u.job_title),
            Builtin(
                "assigned_asset_count",
                "Assets",
                "number",
                sort="assigned_asset_count",
                get=lambda u: getattr(u, "assigned_asset_count", ""),
            ),
            Builtin(
                "last_login",
                "Last seen",
                "date",
                sort="last_login",
                get=lambda u: u.last_login.isoformat() if u.last_login else "",
            ),
            Builtin("is_active", "Active", "boolean", visible=False, sort="is_active", get=lambda u: u.is_active),
        ),
    ),
    "departments": TableDef(
        "departments",
        "Departments",
        "/people/departments",
        False,
        (
            SNO,
            Builtin("name", "Department", required=True, search=("name", "code"), sort="name", get=lambda d: d.name),
            Builtin("code", "Code", search=("code",), sort="code", get=lambda d: d.code),
            Builtin(
                "head_detail.full_name",
                "Head",
                "user",
                search=("head__first_name", "head__last_name"),
                get=lambda d: _name(d.head),
            ),
            Builtin("member_count", "People", "number", sort="member_count", get=lambda d: getattr(d, "member_count", "")),
            Builtin("asset_count", "Assets", "number", sort="asset_count", get=lambda d: getattr(d, "asset_count", "")),
            Builtin("is_active", "Active", "boolean", sort="is_active", get=lambda d: d.is_active),
        ),
    ),
    "locations": TableDef(
        "locations",
        "Locations",
        "/catalog/locations",
        False,
        (
            SNO,
            Builtin("name", "Name", required=True, search=("name", "code", "address"), sort="name", get=lambda loc: loc.name),
            Builtin("code", "Code", search=("code",), sort="code", get=lambda loc: loc.code),
            Builtin(
                "parent_name",
                "Within",
                search=("parent__name",),
                sort="parent__name",
                get=lambda loc: loc.parent.name if loc.parent else "",
            ),
            Builtin("asset_count", "Assets", "number", sort="asset_count", get=lambda loc: getattr(loc, "asset_count", "")),
            Builtin("is_active", "Active", "boolean", sort="is_active", get=lambda loc: loc.is_active),
        ),
    ),
    "vendors": TableDef(
        "vendors",
        "Vendors",
        "/catalog/vendors",
        False,
        (
            SNO,
            Builtin("name", "Vendor", required=True, search=("name",), sort="name", get=lambda v: v.name),
            Builtin("contact_name", "Contact", search=("contact_name",), sort="contact_name", get=lambda v: v.contact_name),
            Builtin("email", "Email", search=("email",), sort="email", get=lambda v: v.email),
            Builtin("phone", "Phone", search=("phone",), get=lambda v: v.phone),
            Builtin("asset_count", "Assets", "number", sort="asset_count", get=lambda v: getattr(v, "asset_count", "")),
            Builtin("is_active", "Active", "boolean", visible=False, sort="is_active", get=lambda v: v.is_active),
        ),
    ),
    # Admin-created tables: every data column is custom; rows are TableRecords.
    "custom": TableDef(
        "custom",
        "Custom table",
        "/t/",
        True,
        (
            SNO,
            Builtin("created_at", "Created", "date", sort="created_at", get=lambda r: r.created_at.isoformat()),
            Builtin("updated_at", "Updated", "date", visible=False, sort="updated_at", get=lambda r: r.updated_at.isoformat()),
        ),
    ),
}

# Default singular names for built-in tables.
SINGULAR = {
    "assets": "Asset",
    "receipts": "Goods receipt",
    "handovers": "Handover",
    "maintenance": "Maintenance job",
    "users": "Person",
    "departments": "Department",
    "locations": "Location",
    "vendors": "Vendor",
}

ROUTE_TO_TABLE = {t.route: t.key for t in TABLES.values() if t.key != "custom"}


def table_for_route(route: str) -> str:
    return ROUTE_TO_TABLE.get((route or "").split("?")[0].rstrip("/") or "/", "")


def builtin(table: str, key: str) -> Builtin | None:
    t = TABLES.get(table)
    return next((c for c in t.columns if c.key == key), None) if t else None


def ensure_columns(item, model=None) -> None:
    """Create any missing built-in columns for a table page (idempotent)."""
    from .models import TableColumn

    model = model or TableColumn
    t = TABLES.get(item.table)
    if not t:
        return
    existing = set(model.objects.filter(sidebar_item_id=item.pk).values_list("key", flat=True))
    missing = [c for c in t.columns if c.key not in existing]
    if not missing:
        return
    start = len(existing)
    model.objects.bulk_create(
        [
            model(
                sidebar_item_id=item.pk,
                name=c.name,
                key=c.key,
                column_type=c.type,
                options=c.options,
                width=c.width,
                order=start + i,
                is_visible=c.visible,
                is_required=c.required,
                is_searchable=bool(c.search),
                is_sortable=c.sort is not None,
                is_builtin=True,
                visible_roles=list(c.roles),
            )
            for i, c in enumerate(missing)
        ],
        ignore_conflicts=True,
    )
