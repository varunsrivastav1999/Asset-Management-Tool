import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Notification

logger = logging.getLogger(__name__)

DASHBOARD_GROUP = "dashboard"
# Every authenticated connection joins this group (config changes such as sidebar/dashboard layout).
BROADCAST_GROUP = "broadcast"


def user_group(user_id) -> str:
    return f"user_{user_id}"


def group_send(group: str, payload: dict):
    """Best-effort push to a Channels group; never raises."""
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(group, {"type": "push", "payload": payload})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Channel layer unavailable; realtime push to %s dropped: %s", group, exc)


def serialize(n: Notification) -> dict:
    return {
        "id": n.id,
        "category": n.category,
        "level": n.level,
        "title": n.title,
        "message": n.message,
        "link": n.link,
        "data": n.data,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def notify(
    recipients,
    *,
    title,
    message="",
    category=Notification.Category.SYSTEM,
    level=Notification.Level.INFO,
    link="",
    data=None,
    dedupe_key=None,
) -> list[Notification]:
    """Create notifications and push them over WebSockets once the transaction commits.

    With `dedupe_key`, a recipient never receives the same alert twice.
    """
    users = [u for u in recipients if u is not None and getattr(u, "is_active", True)]
    if not users:
        return []
    if dedupe_key:
        already = set(
            Notification.objects.filter(recipient__in=users, dedupe_key=dedupe_key).values_list("recipient_id", flat=True)
        )
        users = [u for u in users if u.pk not in already]
    objs = [
        Notification(
            recipient=u,
            title=title[:200],
            message=message,
            category=category,
            level=level,
            link=link[:255],
            data=data or {},
            dedupe_key=dedupe_key,
        )
        for u in users
    ]
    created = Notification.objects.bulk_create(objs, ignore_conflicts=bool(dedupe_key))
    if dedupe_key:
        # ignore_conflicts leaves PKs unset; re-read the rows we actually inserted.
        created = list(Notification.objects.filter(recipient__in=users, dedupe_key=dedupe_key))

    def _push():
        for n in created:
            group_send(user_group(n.recipient_id), {"type": "notification", "notification": serialize(n)})

    transaction.on_commit(_push)
    return created


def managers_queryset():
    User = get_user_model()
    return User.objects.filter(is_active=True, role__in=[User.Role.ADMIN, User.Role.MANAGER])


def notify_managers(*, exclude=None, **kwargs):
    users = list(managers_queryset())
    if exclude:
        ids = {u.pk for u in exclude}
        users = [u for u in users if u.pk not in ids]
    return notify(users, **kwargs)


def broadcast_dashboard(reason: str, **extra):
    group_send(DASHBOARD_GROUP, {"type": "dashboard.update", "reason": reason, **extra})


def broadcast_all(payload: dict):
    group_send(BROADCAST_GROUP, payload)
