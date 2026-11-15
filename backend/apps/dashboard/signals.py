"""Invalidate cached dashboard stats and push a (debounced) live update when data changes."""

import logging

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.assets.models import Asset
from apps.maintenance.models import MaintenanceRecord
from apps.workflows.models import Handover

from .models import DashboardWidget
from .views import CACHE_KEY

logger = logging.getLogger(__name__)

PENDING_KEY = "dashboard:broadcast-pending"
DEBOUNCE_SECONDS = 2


def _schedule_broadcast(reason: str):
    cache.delete(CACHE_KEY)
    # Coalesce bursts (bulk imports, receipts with many assets) into one push.
    if not cache.add(PENDING_KEY, 1, DEBOUNCE_SECONDS + 3):
        return
    from apps.notifications.tasks import broadcast_dashboard_update

    try:
        if settings.CELERY_TASK_ALWAYS_EAGER:
            broadcast_dashboard_update(reason)
        else:
            broadcast_dashboard_update.apply_async(args=[reason], countdown=DEBOUNCE_SECONDS)
    except Exception:  # noqa: BLE001 - broker down: fall back to immediate push
        logger.warning("Celery unavailable; broadcasting dashboard update inline", exc_info=True)
        broadcast_dashboard_update(reason)


def _on_change(sender, instance, **kwargs):
    reason = sender._meta.model_name
    transaction.on_commit(lambda: _schedule_broadcast(reason))


for model in (Asset, Handover, MaintenanceRecord):
    receiver(post_save, sender=model, dispatch_uid=f"dash-save-{model.__name__}")(_on_change)
    receiver(post_delete, sender=model, dispatch_uid=f"dash-del-{model.__name__}")(_on_change)


def broadcast_layout_change():
    """Widget layout changed: every client refetches its dashboard."""
    from apps.notifications.services import broadcast_all

    transaction.on_commit(lambda: broadcast_all({"type": "dashboard.layout"}))


def _on_widget_change(sender, **kwargs):
    broadcast_layout_change()


post_save.connect(_on_widget_change, sender=DashboardWidget, dispatch_uid="widget-save")
post_delete.connect(_on_widget_change, sender=DashboardWidget, dispatch_uid="widget-delete")
