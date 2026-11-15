"""Bulk CSV / Excel import and export of assets."""

import csv
import datetime
import io
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from rest_framework.exceptions import ValidationError

from .models import Asset, AssetEvent, Category, Location, Vendor
from .services import clean_custom_data, log_event

# (header, attribute getter) — header names are also the import column names.
EXPORT_COLUMNS = [
    ("asset_tag", lambda a: a.asset_tag),
    ("name", lambda a: a.name),
    ("category", lambda a: a.category.name),
    ("status", lambda a: a.status),
    ("condition", lambda a: a.condition),
    ("serial_number", lambda a: a.serial_number or ""),
    ("model", lambda a: a.model),
    ("manufacturer", lambda a: a.manufacturer),
    ("vendor", lambda a: a.vendor.name if a.vendor else ""),
    ("location", lambda a: a.location.code if a.location else ""),
    ("assigned_to", lambda a: a.assigned_to.email if a.assigned_to else ""),
    ("department", lambda a: a.department.code if a.department else ""),
    ("purchase_date", lambda a: a.purchase_date.isoformat() if a.purchase_date else ""),
    ("purchase_cost", lambda a: str(a.purchase_cost) if a.purchase_cost is not None else ""),
    ("currency", lambda a: a.currency),
    ("invoice_number", lambda a: a.invoice_number),
    ("po_number", lambda a: a.po_number),
    ("warranty_expiry", lambda a: a.warranty_expiry.isoformat() if a.warranty_expiry else ""),
    ("maintenance_interval_days", lambda a: a.maintenance_interval_days or ""),
    ("next_maintenance_date", lambda a: a.next_maintenance_date.isoformat() if a.next_maintenance_date else ""),
    ("description", lambda a: a.description),
    ("notes", lambda a: a.notes),
]
READ_ONLY_COLUMNS = {"assigned_to", "department"}
IMPORT_STATUSES = {Asset.Status.IN_STOCK, Asset.Status.IN_REPAIR, Asset.Status.LOST, Asset.Status.RETIRED}
CF_PREFIX = "cf:"


def _safe_cell(value):
    """Neutralise spreadsheet formula injection (CSV injection)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _custom_keys(queryset) -> list[str]:
    keys = set()
    for data in queryset.values_list("custom_data", flat=True):
        if isinstance(data, dict):
            keys.update(data.keys())
    return sorted(keys)


def _rows(queryset):
    keys = _custom_keys(queryset)
    header = [h for h, _ in EXPORT_COLUMNS] + [f"{CF_PREFIX}{k}" for k in keys]
    yield header
    for asset in queryset.iterator(chunk_size=500):
        row = [getter(asset) for _, getter in EXPORT_COLUMNS]
        row += [(asset.custom_data or {}).get(k, "") for k in keys]
        yield [_safe_cell(v) for v in row]


def export_csv(queryset) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in _rows(queryset):
        writer.writerow(row)
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel detects UTF-8


def export_xlsx(queryset) -> bytes:
    wb = Workbook(write_only=False)
    ws = wb.active
    ws.title = "Assets"
    for i, row in enumerate(_rows(queryset)):
        ws.append(row)
        if i == 0:
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1E293B")
    ws.freeze_panes = "A2"
    for column in ws.columns:
        width = max(len(str(c.value or "")) for c in column[:200])
        ws.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 50)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def template_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Assets"
    header = [h for h, _ in EXPORT_COLUMNS if h not in READ_ONLY_COLUMNS] + [f"{CF_PREFIX}ram_gb"]
    ws.append(header)
    ws.append(
        [
            "",
            "Dell Latitude 7440",
            "Laptops",
            "in_stock",
            "new",
            "SN-123456",
            "Latitude 7440",
            "Dell",
            "Dell Technologies",
            "HQ",
            "2026-01-15",
            "1499.00",
            settings.DEFAULT_CURRENCY,
            "INV-1001",
            "PO-77",
            "2029-01-15",
            "180",
            "",
            "14-inch business laptop",
            "",
            "16",
        ]
    )
    for cell in ws[1]:
        cell.font = Font(bold=True)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _read_rows(upload) -> list[dict]:
    name = (upload.name or "").lower()
    if upload.size > 5 * 1024 * 1024:
        raise ValidationError({"file": "File exceeds 5 MB."})
    if name.endswith(".csv"):
        text = upload.read().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader]
    elif name.endswith(".xlsx"):
        try:
            wb = load_workbook(upload, read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError({"file": "Could not read the Excel file."}) from exc
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            header = [str(h).strip() if h is not None else "" for h in next(it)]
        except StopIteration:
            return []
        rows = []
        for values in it:
            if values is None or all(v in (None, "") for v in values):
                continue
            rows.append({header[i]: v for i, v in enumerate(values) if i < len(header) and header[i]})
    else:
        raise ValidationError({"file": "Upload a .csv or .xlsx file."})
    if len(rows) > settings.MAX_IMPORT_ROWS:
        raise ValidationError({"file": f"At most {settings.MAX_IMPORT_ROWS} rows per import."})
    return rows


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _date(v, field, errors):
    if v in (None, ""):
        return None
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(_text(v)[:10])
    except ValueError:
        errors[field] = "Use YYYY-MM-DD."
        return None


class _Lookup:
    """Caches name/code lookups across rows."""

    def __init__(self):
        self.categories = {c.name.lower(): c for c in Category.objects.all()}
        self.categories.update({c.slug.lower(): c for c in self.categories.values()})
        self.locations = {loc.code.lower(): loc for loc in Location.objects.all()}
        self.locations.update({loc.name.lower(): loc for loc in list(self.locations.values())})
        self.vendors = {v.name.lower(): v for v in Vendor.objects.all()}

    def vendor(self, name):
        key = name.lower()
        if key not in self.vendors:
            self.vendors[key] = Vendor.objects.create(name=name)
        return self.vendors[key]


_TEXT_FIELDS = ("model", "manufacturer", "invoice_number", "po_number", "description", "notes")


class _RowParser:
    """Validates one import row. Each `_field` method checks a single column and records its own error."""

    def __init__(self, raw: dict, lookup: _Lookup, seen_tags: set, seen_serials: set):
        self.raw, self.lookup, self.seen_tags, self.seen_serials = raw, lookup, seen_tags, seen_serials
        self.errors: dict = {}
        self.asset: Asset | None = None

    def cell(self, key: str) -> str:
        return _text(self.raw.get(key))

    def parse(self) -> tuple[Asset | None, str, dict]:
        """Returns (existing asset or None, status for new assets, field values) — check `errors` first."""
        self.asset = self._existing_asset()
        category = self._category()
        values = {
            "name": self._name(),
            "category": category,
            "condition": self._condition(),
            "serial_number": self._serial(),
            "vendor": self.lookup.vendor(self.cell("vendor")) if self.cell("vendor") else None,
            "location": self._location(),
            "purchase_date": _date(self.raw.get("purchase_date"), "purchase_date", self.errors),
            "purchase_cost": self._cost(),
            "currency": self._currency(),
            "warranty_expiry": _date(self.raw.get("warranty_expiry"), "warranty_expiry", self.errors),
            "maintenance_interval_days": self._interval(),
            "next_maintenance_date": _date(self.raw.get("next_maintenance_date"), "next_maintenance_date", self.errors),
            "custom_data": self._custom_data(category),
            **{key: self.cell(key) for key in _TEXT_FIELDS},
        }
        return self.asset, self._status(), values

    def _existing_asset(self):
        tag = self.cell("asset_tag").upper()
        if not tag:
            return None
        if tag in self.seen_tags:
            self.errors["asset_tag"] = "Duplicate asset_tag in file."
        self.seen_tags.add(tag)
        asset = Asset.objects.filter(asset_tag=tag).first()
        if asset is None:
            self.errors["asset_tag"] = "Unknown asset_tag (leave blank to create a new asset)."
        return asset

    def _name(self):
        name = self.cell("name") or (self.asset.name if self.asset else "")
        if not name:
            self.errors["name"] = "Required."
        return name

    def _category(self):
        key = self.cell("category").lower()
        category = self.lookup.categories.get(key) if key else (self.asset.category if self.asset else None)
        if category is None:
            self.errors["category"] = f"Unknown category '{self.raw.get('category') or ''}'."
        return category

    def _status(self):
        value = self.cell("status").lower()
        if value and self.asset is None and value not in IMPORT_STATUSES:
            self.errors["status"] = f"Must be one of: {', '.join(sorted(IMPORT_STATUSES))}."
        return value

    def _condition(self):
        value = self.cell("condition").lower()
        if value and value not in Asset.Condition.values:
            self.errors["condition"] = f"Must be one of: {', '.join(Asset.Condition.values)}."
        return value or (self.asset.condition if self.asset else Asset.Condition.NEW)

    def _serial(self):
        serial = self.cell("serial_number") or None
        if not serial:
            return self.asset.serial_number if self.asset else None
        if serial in self.seen_serials:
            self.errors["serial_number"] = "Duplicate serial number in file."
        self.seen_serials.add(serial)
        clash = Asset.objects.filter(serial_number=serial)
        if self.asset:
            clash = clash.exclude(pk=self.asset.pk)
        if clash.exists():
            self.errors["serial_number"] = "Serial number already exists."
        return serial

    def _location(self):
        key = self.cell("location").lower()
        if not key:
            return None
        location = self.lookup.locations.get(key)
        if location is None:
            self.errors["location"] = f"Unknown location '{self.raw.get('location')}'."
        return location

    def _cost(self):
        raw = self.cell("purchase_cost")
        if not raw:
            return None
        try:
            cost = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            cost = None
        if cost is None or cost < 0:
            self.errors["purchase_cost"] = "Must be a positive number."
            return None
        return cost

    def _interval(self):
        raw = self.cell("maintenance_interval_days")
        if not raw:
            return None
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
        self.errors["maintenance_interval_days"] = "Must be a positive whole number."
        return None

    def _currency(self):
        currency = self.cell("currency").upper() or (self.asset.currency if self.asset else settings.DEFAULT_CURRENCY)
        if len(currency) != 3:
            self.errors["currency"] = "Use a 3-letter code."
        return currency

    def _custom_data(self, category):
        if category is None:
            return {}
        incoming = {k[len(CF_PREFIX) :]: v for k, v in self.raw.items() if k and k.startswith(CF_PREFIX) and v not in (None, "")}
        existing = self.asset.custom_data if self.asset else None
        try:
            custom = clean_custom_data(category, incoming, partial_existing=existing)
        except ValidationError as exc:
            self.errors.update({f"{CF_PREFIX}{k}": v for k, v in exc.detail.get("custom_data", {}).items()})
            return {}
        if self.asset:  # keep custom table-column values that aren't category fields
            keys = {f.key for f in category.all_custom_fields()}
            custom = {**{k: v for k, v in (self.asset.custom_data or {}).items() if k not in keys}, **custom}
        return custom


def _apply_update(asset: Asset, values: dict) -> None:
    for key, value in values.items():
        if key in _TEXT_FIELDS and value == "":
            continue  # blank cells don't wipe existing text on update
        if value is None and key != "serial_number":
            continue
        setattr(asset, key, value)
    asset.save()


def import_assets(upload, actor, *, dry_run: bool = False) -> dict:
    rows = _read_rows(upload)
    report = {"total": len(rows), "created": 0, "updated": 0, "errors": [], "dry_run": dry_run}
    if not rows:
        report["errors"].append({"row": 1, "errors": {"file": "No data rows found."}})
        return report
    lookup = _Lookup()
    seen_tags, seen_serials = set(), set()

    with transaction.atomic():
        savepoint = transaction.savepoint()
        for index, raw in enumerate(rows, start=2):  # row 1 is the header
            parser = _RowParser(raw, lookup, seen_tags, seen_serials)
            asset, status_value, values = parser.parse()
            if parser.errors:
                report["errors"].append({"row": index, "errors": parser.errors})
                continue
            if asset is None:
                asset = Asset.objects.create(status=status_value or Asset.Status.IN_STOCK, created_by=actor, **values)
                log_event(asset, AssetEvent.Type.IMPORTED, actor, to_status=asset.status, notes="Created by bulk import")
                report["created"] += 1
            else:
                _apply_update(asset, values)
                log_event(asset, AssetEvent.Type.UPDATED, actor, notes="Updated by bulk import")
                report["updated"] += 1

        if dry_run or report["errors"]:
            transaction.savepoint_rollback(savepoint)
            if report["errors"]:
                report["created"] = report["updated"] = 0
        else:
            transaction.savepoint_commit(savepoint)
    report["finished_at"] = timezone.now().isoformat()
    return report
