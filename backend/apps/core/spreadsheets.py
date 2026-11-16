"""Reading uploaded spreadsheets (CSV or Excel) for bulk imports."""

import csv
import io

from django.conf import settings
from openpyxl import load_workbook
from rest_framework.exceptions import ValidationError

MAX_IMPORT_MB = 5


def read_rows(upload) -> list[dict]:
    """Rows of a .csv / .xlsx upload as {header: value}; size and row count are limited."""
    name = (upload.name or "").lower()
    if upload.size > MAX_IMPORT_MB * 1024 * 1024:
        raise ValidationError({"file": f"File exceeds {MAX_IMPORT_MB} MB."})
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
