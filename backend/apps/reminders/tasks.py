import datetime
import logging

from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.core.files import private_storage

from .engine import compute_next_run, queue_rule
from .models import ChannelConfig, ReminderLog, ReminderRule
from .providers import DeliveryError, get_sms_provider, send_email

logger = logging.getLogger(__name__)
MAX_RETRIES = 5


@shared_task
def scan_reminder_rules() -> int:
    """Beat entry point (every few minutes): claim due rules and queue one task per rule."""
    now = timezone.now()
    queued = 0
    with transaction.atomic():
        due = ReminderRule.objects.select_for_update(skip_locked=True).filter(is_active=True, next_run_at__lte=now)
        for rule in due:
            rule.next_run_at = compute_next_run(rule.schedule, now)  # claim before queuing → never double-runs
            rule.save(update_fields=["next_run_at"])
            transaction.on_commit(lambda pk=rule.pk: run_rule.delay(pk))
            queued += 1
        # Active rules that were never scheduled get their first run time.
        for rule in ReminderRule.objects.filter(is_active=True, next_run_at__isnull=True).exclude(schedule__kind="manual"):
            nxt = compute_next_run(rule.schedule, now)
            if nxt:
                ReminderRule.objects.filter(pk=rule.pk).update(next_run_at=nxt)
    return queued


@shared_task
def run_rule(rule_id: int, run_tag: str = "", test_user_id: int | None = None) -> int:
    from django.contrib.auth import get_user_model

    rule = ReminderRule.objects.select_related("template", "section", "created_by").filter(pk=rule_id).first()
    if rule is None:
        return 0
    test_user = get_user_model().objects.filter(pk=test_user_id).first() if test_user_id else None
    logs = queue_rule(rule, run_tag=run_tag, test_user=test_user)
    if test_user is None:
        ReminderRule.objects.filter(pk=rule.pk).update(last_run_at=timezone.now())
    for log in logs:
        if log.deliver_after and log.deliver_after > timezone.now():
            deliver_log.apply_async(args=[log.pk], eta=log.deliver_after)
        else:
            deliver_log.delay(log.pk)
    return len(logs)


def _over_rate(channel: str, per_minute: int) -> bool:
    key = f"reminders:rate:{channel}:{timezone.now():%Y%m%d%H%M}"
    cache.add(key, 0, 120)
    try:
        return cache.incr(key) > per_minute
    except ValueError:
        return False


def _over_daily_cap(cap: int) -> bool:
    key = f"reminders:cap:{timezone.localdate():%Y%m%d}"
    cache.add(key, 0, 60 * 60 * 26)
    try:
        return cache.incr(key) > cap
    except ValueError:
        return False


def _alert_admins(log: ReminderLog):
    from django.contrib.auth import get_user_model

    from apps.notifications.models import Notification
    from apps.notifications.services import notify

    admins = list(get_user_model().objects.filter(is_active=True, role="admin"))
    notify(
        admins,
        title=f"Reminder delivery failing: {log.rule_name or 'reminder'}",
        message=f"{log.channel} to {log.recipient_address} failed after {log.attempts} attempt(s): {log.error[:200]}",
        category=Notification.Category.SYSTEM,
        level=Notification.Level.CRITICAL,
        link="/reminders?tab=logs&status=failed",
        dedupe_key=f"reminder-failure:{log.rule_id}:{timezone.localdate().isoformat()}",
    )


@shared_task(bind=True, max_retries=MAX_RETRIES)
def deliver_log(self, log_id: int) -> str:
    """Send one queued message. Idempotent: only 'queued' logs are sent, under a per-log lock."""
    lock = f"reminders:sending:{log_id}"
    if not cache.add(lock, 1, 300):
        return "busy"
    try:
        log = ReminderLog.objects.filter(pk=log_id, status=ReminderLog.Status.QUEUED).first()
        if log is None:
            return "skip"
        config = ChannelConfig.load()
        if log.channel in ("email", "sms"):
            per_minute = config.email_per_minute if log.channel == "email" else config.sms_per_minute
            if _over_rate(log.channel, per_minute):
                cache.delete(lock)
                raise self.retry(countdown=60, max_retries=MAX_RETRIES + 50)  # throttled, not a failure
            if _over_daily_cap(config.daily_cap):
                ReminderLog.objects.filter(pk=log.pk).update(status=ReminderLog.Status.FAILED, error="Daily send cap reached.")
                log.refresh_from_db()
                _alert_admins(log)
                return "capped"
        attempts = log.attempts + 1
        try:
            provider_id = _send(log, config)
        except DeliveryError as exc:
            error = str(exc)[:2000]
            if self.request.retries < MAX_RETRIES:
                ReminderLog.objects.filter(pk=log.pk).update(attempts=attempts, error=error)
                cache.delete(lock)
                raise self.retry(exc=exc, countdown=min(3600, 30 * 2**self.request.retries)) from exc  # 30s, 1m, 2m, 4m, 8m
            ReminderLog.objects.filter(pk=log.pk).update(attempts=attempts, error=error, status=ReminderLog.Status.FAILED)
            log.refresh_from_db()
            _alert_admins(log)
            return "failed"
        ReminderLog.objects.filter(pk=log.pk).update(
            attempts=attempts, status=ReminderLog.Status.SENT, sent_at=timezone.now(), error="", provider_message_id=provider_id
        )
        return "sent"
    finally:
        cache.delete(lock)


def _send(log: ReminderLog, config: ChannelConfig) -> str:
    if log.channel == "email":
        files, links = [], []
        for a in log.attachments:
            if a.get("link"):
                links.append((a["name"], a["link"]))
                continue
            with private_storage.open(a["path"], "rb") as fh:
                files.append((a["name"], fh.read(), a.get("mimetype", "application/octet-stream")))
        text = log.message
        html = log.html
        if links:
            text += "\n\nDownloads (links expire):\n" + "\n".join(f"{n}: {u}" for n, u in links)
            html += "".join(f'<p><a href="{u}">{n}</a> (link expires)</p>' for n, u in links)
        return send_email(log.recipient_address, log.subject, text, html, files, config.sender_name)
    if log.channel == "sms":
        return get_sms_provider(config.sms_provider).send(log.recipient_address, log.message, config.sms_sender_id)
    from apps.notifications.services import notify

    if log.recipient:
        notify([log.recipient], title=log.subject, message=log.message, link=log.link.replace(_frontend(), ""))
    return "in-app"


def _frontend() -> str:
    from django.conf import settings

    return settings.FRONTEND_URL


@shared_task
def purge_reminder_files(days: int = 7) -> int:
    """Remove generated attachment files older than `days` (links expire well before)."""
    cutoff = timezone.now() - datetime.timedelta(days=days)
    removed = 0
    for log in ReminderLog.objects.filter(created_at__lt=cutoff).exclude(attachments=[]).only("attachments"):
        for a in log.attachments:
            if private_storage.exists(a.get("path", "")):
                private_storage.delete(a["path"])
                removed += 1
    return removed
