"""Bulk import of rows into a custom table from CSV / Excel.

Headers are matched to the table's columns by name or key (case-insensitive). Every cell is validated with the
same rules as typing it in the app (`coerce_value`), required columns are enforced, and the whole file is
all-or-nothing: if any row fails, nothing is saved. `dry_run` validates without saving.
"""

import csv
import datetime
import io

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.core.spreadsheets import read_rows

from .models import TableColumn, TableRecord
from .table_api import coerce_value

T = TableColumn.Type
NOT_IMPORTABLE = {T.MEDIA: "Media can't be imported from a spreadsheet; upload files in the table."}


def importable_columns(item) -> list[TableColumn]:
    """The table's own (non built-in) columns, in display order."""
    return list(TableColumn.objects.filter(sidebar_item=item, is_builtin=False).order_by("order", "id"))


def template_csv(item) -> bytes:
    """Header row the import expects (UTF-8 with BOM so Excel opens it correctly)."""
    out = io.StringIO()
    csv.writer(out).writerow([c.name for c in importable_columns(item) if c.column_type not in NOT_IMPORTABLE])
    return ("﻿" + out.getvalue()).encode("utf-8")


def _normalise(raw):
    """Spreadsheet values -> what `coerce_value` accepts (Excel gives dates/numbers, not text)."""
    if isinstance(raw, datetime.datetime):
        return raw.date().isoformat()
    if isinstance(raw, datetime.date):
        return raw.isoformat()
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    return raw.strip() if isinstance(raw, str) else raw


class _UserLookup:
    """Resolves a person by email or full name, cached across rows."""

    def __init__(self):
        self.cache = {}

    def __call__(self, text: str):
        key = text.strip().lower()
        if key not in self.cache:
            User = get_user_model()
            qs = User.objects.filter(is_active=True)
            user = qs.filter(email__iexact=key).first()
            if user is None:
                parts = text.split()
                if len(parts) >= 2:
                    matches = list(qs.filter(Q(first_name__iexact=parts[0]) & Q(last_name__iexact=" ".join(parts[1:])))[:2])
                    user = matches[0] if len(matches) == 1 else None
            self.cache[key] = user
        user = self.cache[key]
        return {"id": user.pk, "name": user.get_full_name() or user.email} if user else None


def import_records(item, upload, actor, *, dry_run: bool = False) -> dict:
    rows = read_rows(upload)
    report = {"total": len(rows), "created": 0, "updated": 0, "errors": [], "ignored_columns": [], "dry_run": dry_run}
    if not rows:
        report["errors"].append({"row": 1, "errors": {"file": "No data rows found."}})
        return report

    columns = importable_columns(item)
    by_label = {}
    for col in columns:
        by_label[col.name.strip().lower()] = col
        by_label[col.key.lower()] = col
    headers = list(rows[0].keys())
    matched = {h: by_label.get(h.strip().lower()) for h in headers}
    report["ignored_columns"] = [h for h, c in matched.items() if c is None and h]
    present = {c.key for c in matched.values() if c is not None}
    missing = [c.name for c in columns if c.is_required and c.key not in present]
    if missing:
        report["errors"].append({"row": 1, "errors": {"file": f"Missing required column(s): {', '.join(missing)}."}})
        return report

    find_user = _UserLookup()
    definition = item.definition
    with transaction.atomic():
        savepoint = transaction.savepoint()
        for index, raw_row in enumerate(rows, start=2):  # row 1 is the header
            data, errors = {}, {}
            for header, col in matched.items():
                if col is None:
                    continue
                raw = _normalise(raw_row.get(header))
                if raw in (None, ""):
                    continue
                if col.column_type in NOT_IMPORTABLE:
                    errors[col.name] = NOT_IMPORTABLE[col.column_type]
                    continue
                if col.column_type == T.USER and isinstance(raw, str):
                    raw = find_user(raw)
                    if raw is None:
                        errors[col.name] = "No active person with that email or name."
                        continue
                try:
                    value = coerce_value(col, raw)
                except DomainError as exc:
                    errors[col.name] = exc.message
                    continue
                if value is not None:
                    data[col.key] = value
            for col in columns:
                if col.is_required and col.key not in data and col.name not in errors:
                    errors[col.name] = "Required."
            if errors:
                report["errors"].append({"row": index, "errors": errors})
                continue
            TableRecord.objects.create(definition=definition, custom_data=data, created_by=actor)
            report["created"] += 1

        if dry_run or report["errors"]:
            transaction.savepoint_rollback(savepoint)
            if report["errors"]:
                report["created"] = 0
        else:
            transaction.savepoint_commit(savepoint)
    report["finished_at"] = timezone.now().isoformat()
    return report
