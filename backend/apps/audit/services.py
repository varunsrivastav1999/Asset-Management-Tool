import datetime
import decimal
import logging
import uuid

from django.db import models
from django.db.models.fields.files import FieldFile

from apps.core.middleware import get_request_context

from .models import AuditLog

logger = logging.getLogger(__name__)

SKIP_FIELDS = {"password", "updated_at", "created_at", "last_login"}


def _jsonable(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, (decimal.Decimal, uuid.UUID)):
        return str(value)
    if isinstance(value, FieldFile):
        return value.name or None
    if isinstance(value, models.Model):
        return value.pk
    return value


def snapshot(instance: models.Model) -> dict:
    """Concrete field values of a model instance, JSON-safe."""
    data = {}
    for field in instance._meta.concrete_fields:
        if field.name in SKIP_FIELDS:
            continue
        data[field.attname] = _jsonable(getattr(instance, field.attname))
    return data


def diff(before: dict, after: dict) -> dict:
    keys = set(before) | set(after)
    return {k: {"from": before.get(k), "to": after.get(k)} for k in sorted(keys) if before.get(k) != after.get(k)}


def record(action, actor=None, instance=None, changes=None, *, model="", object_id="", object_repr=""):
    ctx = get_request_context()
    if instance is not None:
        model = model or instance._meta.label_lower
        object_id = object_id or str(instance.pk)
        object_repr = object_repr or str(instance)[:255]
    try:
        return AuditLog.objects.create(
            actor=actor if (actor is not None and getattr(actor, "is_authenticated", False)) else None,
            action=action,
            model=model,
            object_id=str(object_id or ""),
            object_repr=object_repr[:255],
            changes=changes or {},
            ip_address=ctx.get("ip"),
            user_agent=ctx.get("user_agent", ""),
            request_id=ctx.get("request_id", ""),
        )
    except Exception:  # noqa: BLE001 - auditing must never break the business operation
        logger.exception("Failed to write audit log entry")
        return None


class AuditedViewSetMixin:
    """Writes create/update/delete audit entries for ModelViewSet writes."""

    def perform_create(self, serializer):
        instance = serializer.save(**self.get_save_kwargs(created=True))
        record(AuditLog.Action.CREATE, self.request.user, instance, {"after": snapshot(instance)})
        return instance

    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        instance = serializer.save(**self.get_save_kwargs(created=False))
        changes = diff(before, snapshot(instance))
        if changes:
            record(AuditLog.Action.UPDATE, self.request.user, instance, changes)
        return instance

    def perform_destroy(self, instance):
        before = snapshot(instance)
        repr_, pk = str(instance), instance.pk
        label = instance._meta.label_lower
        instance.delete()
        record(
            AuditLog.Action.DELETE,
            self.request.user,
            changes={"before": before},
            model=label,
            object_id=pk,
            object_repr=repr_,
        )

    def get_save_kwargs(self, created: bool) -> dict:
        return {}
