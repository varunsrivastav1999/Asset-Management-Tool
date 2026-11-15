import datetime

from django.db import transaction
from django.utils import timezone

from apps.assets.models import Asset, AssetEvent
from apps.assets.services import log_event
from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.exceptions import DomainError

from .models import MaintenanceRecord

R = MaintenanceRecord.Status


@transaction.atomic
def start(rec: MaintenanceRecord, actor) -> MaintenanceRecord:
    rec = MaintenanceRecord.objects.select_for_update(of=("self",)).get(pk=rec.pk)
    if rec.status != R.SCHEDULED:
        raise DomainError("Only scheduled maintenance can be started.")
    asset = Asset.objects.select_for_update(of=("self",)).get(pk=rec.asset_id)
    if asset.status in (Asset.Status.RETIRED, Asset.Status.LOST):
        raise DomainError(f"Asset is {asset.get_status_display().lower()}.")
    if MaintenanceRecord.objects.filter(asset=asset, status=R.IN_PROGRESS).exclude(pk=rec.pk).exists():
        raise DomainError("This asset already has maintenance in progress.")
    rec.previous_asset_status = asset.status
    rec.status = R.IN_PROGRESS
    rec.started_at = timezone.now()
    rec.save()
    if asset.status != Asset.Status.IN_REPAIR:
        prev = asset.status
        asset.status = Asset.Status.IN_REPAIR
        asset.save(update_fields=["status", "updated_at"])
        log_event(
            asset,
            AssetEvent.Type.MAINTENANCE_STARTED,
            actor,
            from_status=prev,
            to_status=asset.status,
            maintenance=rec,
            notes=rec.title,
        )
    record(AuditLog.Action.STATUS_CHANGE, actor, rec, {"status": {"from": R.SCHEDULED, "to": R.IN_PROGRESS}})
    return rec


@transaction.atomic
def complete(rec: MaintenanceRecord, actor, *, cost=None, notes="", completed_date=None, condition=None) -> MaintenanceRecord:
    rec = MaintenanceRecord.objects.select_for_update(of=("self",)).get(pk=rec.pk)
    if rec.status not in (R.SCHEDULED, R.IN_PROGRESS):
        raise DomainError("This maintenance is already closed.")
    asset = Asset.objects.select_for_update(of=("self",)).get(pk=rec.asset_id)
    was_started = rec.status == R.IN_PROGRESS
    rec.status = R.COMPLETED
    rec.completed_date = completed_date or timezone.localdate()
    if cost is not None:
        rec.cost = cost
    if notes:
        rec.notes = f"{rec.notes}\n{notes}".strip()
    rec.save()

    prev = asset.status
    if was_started and asset.status == Asset.Status.IN_REPAIR:
        asset.status = Asset.Status.ASSIGNED if asset.has_holder else Asset.Status.IN_STOCK
    if condition in Asset.Condition.values:
        asset.condition = condition
    if asset.maintenance_interval_days:
        asset.next_maintenance_date = rec.completed_date + datetime.timedelta(days=asset.maintenance_interval_days)
    elif asset.next_maintenance_date and asset.next_maintenance_date <= rec.completed_date:
        asset.next_maintenance_date = None
    asset.save()
    log_event(
        asset,
        AssetEvent.Type.MAINTENANCE_COMPLETED,
        actor,
        from_status=prev,
        to_status=asset.status,
        maintenance=rec,
        notes=rec.title,
        metadata={"cost": str(rec.cost) if rec.cost is not None else None},
    )
    record(AuditLog.Action.STATUS_CHANGE, actor, rec, {"status": {"to": R.COMPLETED}})
    return rec


@transaction.atomic
def cancel(rec: MaintenanceRecord, actor) -> MaintenanceRecord:
    rec = MaintenanceRecord.objects.select_for_update(of=("self",)).get(pk=rec.pk)
    if rec.status not in (R.SCHEDULED, R.IN_PROGRESS):
        raise DomainError("This maintenance is already closed.")
    asset = Asset.objects.select_for_update(of=("self",)).get(pk=rec.asset_id)
    if rec.status == R.IN_PROGRESS and asset.status == Asset.Status.IN_REPAIR:
        asset.status = Asset.Status.ASSIGNED if asset.has_holder else Asset.Status.IN_STOCK
        asset.save(update_fields=["status", "updated_at"])
    rec.status = R.CANCELLED
    rec.save(update_fields=["status", "updated_at"])
    record(AuditLog.Action.CANCEL, actor, rec)
    return rec
