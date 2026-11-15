import datetime
import logging

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.assets.models import Asset
from apps.maintenance.models import MaintenanceRecord

from .models import Notification
from .services import broadcast_dashboard, managers_queryset, notify

logger = logging.getLogger(__name__)


def _recipients(asset):
    users = list(managers_queryset())
    if asset.assigned_to and asset.assigned_to not in users:
        users.append(asset.assigned_to)
    return users


@shared_task
def check_warranty_expiry() -> int:
    """Alert managers (and the holder) at each configured threshold before warranty expiry."""
    today = timezone.localdate()
    thresholds = sorted(set(settings.WARRANTY_ALERT_DAYS), reverse=True)
    horizon = today + datetime.timedelta(days=max(thresholds))
    assets = (
        Asset.objects.filter(
            warranty_expiry__isnull=False, warranty_expiry__lte=horizon, warranty_expiry__gte=today - datetime.timedelta(days=1)
        )
        .exclude(status__in=[Asset.Status.RETIRED, Asset.Status.LOST])
        .select_related("assigned_to")
    )
    sent = 0
    for asset in assets:
        days_left = (asset.warranty_expiry - today).days
        # The tightest threshold the asset has crossed, e.g. 30 → 7 → 0.
        crossed = [t for t in thresholds if days_left <= t]
        if not crossed:
            continue
        threshold = min(crossed)
        expired = days_left <= 0
        title = f"Warranty {'expired' if expired else 'expiring'}: {asset.asset_tag}"
        message = (
            f"{asset.name} warranty expired on {asset.warranty_expiry:%d %b %Y}."
            if expired
            else f"{asset.name} warranty expires in {days_left} day(s) on {asset.warranty_expiry:%d %b %Y}."
        )
        sent += len(
            notify(
                _recipients(asset),
                title=title,
                message=message,
                category=Notification.Category.WARRANTY,
                level=Notification.Level.CRITICAL if threshold <= 7 else Notification.Level.WARNING,
                link=f"/assets/{asset.pk}",
                data={"asset": asset.pk, "days_left": days_left},
                dedupe_key=f"warranty:{asset.pk}:{asset.warranty_expiry.isoformat()}:{threshold}",
            )
        )
    logger.info("Warranty alerts sent: %s", sent)
    return sent


@shared_task
def check_maintenance_due() -> int:
    today = timezone.localdate()
    limit = today + datetime.timedelta(days=settings.MAINTENANCE_ALERT_DAYS)
    sent = 0
    assets = (
        Asset.objects.filter(next_maintenance_date__isnull=False, next_maintenance_date__lte=limit)
        .exclude(status__in=[Asset.Status.RETIRED, Asset.Status.LOST, Asset.Status.IN_REPAIR])
        .select_related("assigned_to")
    )
    for asset in assets:
        days = (asset.next_maintenance_date - today).days
        overdue = days < 0
        sent += len(
            notify(
                _recipients(asset),
                title=f"Maintenance {'overdue' if overdue else 'due'}: {asset.asset_tag}",
                message=f"{asset.name} maintenance {'was due' if overdue else 'is due'} on {asset.next_maintenance_date:%d %b %Y}.",
                category=Notification.Category.MAINTENANCE,
                level=Notification.Level.CRITICAL if overdue else Notification.Level.WARNING,
                link=f"/assets/{asset.pk}",
                data={"asset": asset.pk, "days": days},
                dedupe_key=f"maint:{asset.pk}:{asset.next_maintenance_date.isoformat()}:{'overdue' if overdue else 'due'}",
            )
        )
    records = MaintenanceRecord.objects.filter(
        status=MaintenanceRecord.Status.SCHEDULED, scheduled_date__lte=today + datetime.timedelta(days=2)
    ).select_related("asset")
    for rec in records:
        sent += len(
            notify(
                list(managers_queryset()),
                title=f"Scheduled maintenance: {rec.asset.asset_tag}",
                message=f"{rec.title} is scheduled for {rec.scheduled_date:%d %b %Y}.",
                category=Notification.Category.MAINTENANCE,
                level=Notification.Level.INFO,
                link="/maintenance",
                data={"maintenance": rec.pk},
                dedupe_key=f"maintrec:{rec.pk}:{rec.scheduled_date.isoformat()}",
            )
        )
    logger.info("Maintenance alerts sent: %s", sent)
    return sent


@shared_task
def check_overdue_returns() -> int:
    from apps.workflows.models import Handover

    today = timezone.localdate()
    sent = 0
    handovers = Handover.objects.filter(
        type=Handover.Type.ISSUE,
        status=Handover.Status.COMPLETED,
        expected_return_date__lt=today,
        overdue_notified=False,
    ).select_related("to_user")
    for h in handovers:
        still_out = h.items.filter(
            Q(asset__assigned_to=h.to_user) if h.to_user_id else Q(asset__department=h.to_department),
            asset__status=Asset.Status.ASSIGNED,
        ).count()
        if still_out:
            recipients = list(managers_queryset())
            if h.to_user:
                recipients.append(h.to_user)
            sent += len(
                notify(
                    recipients,
                    title=f"Return overdue: {h.reference}",
                    message=f"{still_out} asset(s) were due back on {h.expected_return_date:%d %b %Y}.",
                    category=Notification.Category.HANDOVER,
                    level=Notification.Level.WARNING,
                    link=f"/handovers/{h.pk}",
                    dedupe_key=f"overdue:{h.pk}",
                )
            )
        h.overdue_notified = True
        h.save(update_fields=["overdue_notified"])
    return sent


@shared_task
def broadcast_dashboard_update(reason: str = "change") -> None:
    from django.core.cache import cache

    cache.delete("dashboard:broadcast-pending")
    broadcast_dashboard(reason)
