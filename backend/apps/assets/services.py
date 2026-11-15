import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.exceptions import DomainError

from .models import Asset, AssetEvent, CustomField

S = Asset.Status


def log_event(asset: Asset, event_type: str, actor=None, **fields) -> AssetEvent:
    return AssetEvent.objects.create(asset=asset, event_type=event_type, actor=actor, **fields)


def status_change_error(asset: Asset, target: str) -> str | None:
    """Return a human-readable reason why `asset` cannot move to `target`, or None if allowed."""
    current = asset.status
    if target not in S.values:
        return "Unknown status."
    if target == current:
        return f"Asset is already {asset.get_status_display().lower()}."
    if current == S.RETIRED and target != S.IN_STOCK:
        return "Retired assets can only be reinstated to stock."
    if target == S.IN_STOCK and asset.has_holder:
        return "Asset is held by someone — record a return handover instead."
    if target == S.ASSIGNED and not asset.has_holder:
        return "Asset has no holder — issue it with a handover instead."
    if target == S.RETIRED and asset.has_holder:
        return "Return the asset before retiring it."
    return None


@transaction.atomic
def change_status(asset: Asset, target: str, actor=None, notes: str = "", **event_fields) -> Asset:
    asset = Asset.objects.select_for_update(of=("self",)).get(pk=asset.pk)
    error = status_change_error(asset, target)
    if error:
        raise DomainError(error, code="invalid_transition", field="status")
    previous = asset.status
    asset.status = target
    asset.save(update_fields=["status", "updated_at"])
    log_event(asset, AssetEvent.Type.STATUS_CHANGED, actor, from_status=previous, to_status=target, notes=notes, **event_fields)
    record(AuditLog.Action.STATUS_CHANGE, actor, asset, {"status": {"from": previous, "to": target}, "notes": notes})
    return asset


def _coerce(field: CustomField, value):
    t = CustomField.FieldType
    if field.field_type == t.TEXT:
        value = str(value).strip()
        if len(value) > 1000:
            raise ValueError("must be at most 1000 characters")
        return value
    if field.field_type == t.NUMBER:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("must be a number") from exc
        if not number.is_finite():
            raise ValueError("must be a number")
        return float(number) if number != number.to_integral_value() else int(number)
    if field.field_type == t.DATE:
        if isinstance(value, datetime.datetime):
            return value.date().isoformat()
        if isinstance(value, datetime.date):
            return value.isoformat()
        try:
            return datetime.date.fromisoformat(str(value).strip()[:10]).isoformat()
        except ValueError as exc:
            raise ValueError("must be a date (YYYY-MM-DD)") from exc
    if field.field_type == t.BOOLEAN:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return True
        if text in {"false", "0", "no", "n"}:
            return False
        raise ValueError("must be yes or no")
    if field.field_type == t.SELECT:
        value = str(value).strip()
        if field.options and value not in field.options:
            raise ValueError(f"must be one of: {', '.join(map(str, field.options))}")
        return value
    return value


def clean_custom_data(category, data: dict | None, *, partial_existing: dict | None = None) -> dict:
    """Validate custom field values against a category's (inherited) field definitions.

    Unknown keys are dropped. Raises DomainError keyed on `custom_data` with per-field messages.
    """
    if data is not None and not isinstance(data, dict):
        raise DomainError("Custom data must be an object.", field="custom_data")
    data = dict(data or {})
    cleaned, errors = {}, {}
    for field in category.all_custom_fields():
        raw = data.get(field.key, (partial_existing or {}).get(field.key))
        if raw is None or raw == "":
            if field.required:
                errors[field.key] = f"{field.label} is required."
            continue
        try:
            cleaned[field.key] = _coerce(field, raw)
        except ValueError as exc:
            errors[field.key] = f"{field.label} {exc}."
    if errors:
        from rest_framework.exceptions import ValidationError

        raise ValidationError({"custom_data": errors})
    return cleaned
