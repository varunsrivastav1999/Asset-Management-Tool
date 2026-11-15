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
            "USD",
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
            errors = {}
            tag = _text(raw.get("asset_tag")).upper()
            asset = None
            if tag:
                if tag in seen_tags:
                    errors["asset_tag"] = "Duplicate asset_tag in file."
                seen_tags.add(tag)
                asset = Asset.objects.filter(asset_tag=tag).first()
                if asset is None:
                    errors["asset_tag"] = "Unknown asset_tag (leave blank to create a new asset)."
            name = _text(raw.get("name")) or (asset.name if asset else "")
            if not name:
                errors["name"] = "Required."
            cat_key = _text(raw.get("category")).lower()
            category = lookup.categories.get(cat_key) if cat_key else (asset.category if asset else None)
            if category is None:
                errors["category"] = f"Unknown category '{raw.get('category') or ''}'."
            status_value = _text(raw.get("status")).lower()
            if status_value and asset is None and status_value not in IMPORT_STATUSES:
                errors["status"] = f"Must be one of: {', '.join(sorted(IMPORT_STATUSES))}."
            condition = _text(raw.get("condition")).lower()
            if condition and condition not in Asset.Condition.values:
                errors["condition"] = f"Must be one of: {', '.join(Asset.Condition.values)}."
            serial = _text(raw.get("serial_number")) or None
            if serial:
                if serial in seen_serials:
                    errors["serial_number"] = "Duplicate serial number in file."
                seen_serials.add(serial)
                clash = Asset.objects.filter(serial_number=serial)
                if asset:
                    clash = clash.exclude(pk=asset.pk)
                if clash.exists():
                    errors["serial_number"] = "Serial number already exists."
            location = None
            loc_key = _text(raw.get("location")).lower()
            if loc_key:
                location = lookup.locations.get(loc_key)
                if location is None:
                    errors["location"] = f"Unknown location '{raw.get('location')}'."
            cost = None
            cost_raw = _text(raw.get("purchase_cost"))
            if cost_raw:
                try:
                    cost = Decimal(cost_raw.replace(",", ""))
                    if cost < 0:
                        raise InvalidOperation
                except InvalidOperation:
                    errors["purchase_cost"] = "Must be a positive number."
            interval = None
            interval_raw = _text(raw.get("maintenance_interval_days"))
            if interval_raw:
                if interval_raw.isdigit() and int(interval_raw) > 0:
                    interval = int(interval_raw)
                else:
                    errors["maintenance_interval_days"] = "Must be a positive whole number."
            purchase_date = _date(raw.get("purchase_date"), "purchase_date", errors)
            warranty = _date(raw.get("warranty_expiry"), "warranty_expiry", errors)
            next_maint = _date(raw.get("next_maintenance_date"), "next_maintenance_date", errors)
            custom_in = {k[len(CF_PREFIX) :]: v for k, v in raw.items() if k and k.startswith(CF_PREFIX) and v not in (None, "")}
            custom = {}
            if category is not None:
                try:
                    custom = clean_custom_data(category, custom_in, partial_existing=asset.custom_data if asset else None)
                    if asset:  # keep custom table-column values that aren't category fields
                        keys = {f.key for f in category.all_custom_fields()}
                        custom = {**{k: v for k, v in (asset.custom_data or {}).items() if k not in keys}, **custom}
                except ValidationError as exc:
                    errors.update({f"{CF_PREFIX}{k}": v for k, v in exc.detail.get("custom_data", {}).items()})
            currency = _text(raw.get("currency")).upper() or (asset.currency if asset else "USD")
            if len(currency) != 3:
                errors["currency"] = "Use a 3-letter code."

            if errors:
                report["errors"].append({"row": index, "errors": errors})
                continue

            values = {
                "name": name,
                "category": category,
                "condition": condition or (asset.condition if asset else Asset.Condition.NEW),
                "serial_number": serial if serial or not asset else asset.serial_number,
                "model": _text(raw.get("model")),
                "manufacturer": _text(raw.get("manufacturer")),
                "vendor": lookup.vendor(_text(raw.get("vendor"))) if _text(raw.get("vendor")) else None,
                "location": location,
                "purchase_date": purchase_date,
                "purchase_cost": cost,
                "currency": currency,
                "invoice_number": _text(raw.get("invoice_number")),
                "po_number": _text(raw.get("po_number")),
                "warranty_expiry": warranty,
                "maintenance_interval_days": interval,
                "next_maintenance_date": next_maint,
                "description": _text(raw.get("description")),
                "notes": _text(raw.get("notes")),
                "custom_data": custom,
            }
            if asset is None:
                asset = Asset.objects.create(status=status_value or Asset.Status.IN_STOCK, created_by=actor, **values)
                log_event(asset, AssetEvent.Type.IMPORTED, actor, to_status=asset.status, notes="Created by bulk import")
                report["created"] += 1
            else:
                for key, value in values.items():
                    if key in {"model", "manufacturer", "invoice_number", "po_number", "description", "notes"} and value == "":
                        continue  # blank cells don't wipe existing text on update
                    if value is None and key not in {"serial_number"}:
                        continue
                    setattr(asset, key, value)
                asset.save()
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
