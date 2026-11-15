from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class ChannelConfig(models.Model):
    """Global delivery settings (singleton). Secrets (SMTP password, SMS API key) live only in env vars."""

    class SmsProvider(models.TextChoices):
        CONSOLE = "console", "Console (development)"
        TWILIO = "twilio", "Twilio"
        MSG91 = "msg91", "MSG91"

    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    in_app_enabled = models.BooleanField(default=True)
    sender_name = models.CharField(max_length=80, default="Asset Management Tools")
    sms_provider = models.CharField(max_length=16, choices=SmsProvider.choices, default=SmsProvider.CONSOLE)
    sms_sender_id = models.CharField(max_length=11, blank=True, help_text="Alphanumeric sender ID (max 11)")
    daily_cap = models.PositiveIntegerField(default=1000, help_text="Max email+SMS messages per day")
    email_per_minute = models.PositiveIntegerField(default=60)
    sms_per_minute = models.PositiveIntegerField(default=30)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "notification channel settings"
        verbose_name_plural = "notification channel settings"

    def __str__(self):
        return "Notification channels"

    @classmethod
    def load(cls) -> "ChannelConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ReminderTemplate(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    subject = models.CharField(max_length=200)
    body = models.TextField(help_text="Email body; use {{variables}}")
    sms_text = models.CharField(max_length=160, blank=True, help_text="SMS / in-app text (max 160)")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ReminderRule(TimeStampedModel):
    class Trigger(models.TextChoices):
        WARRANTY_EXPIRY = "warranty_expiry", "Warranty expiry"
        MAINTENANCE_DUE = "maintenance_due", "Maintenance due"
        OVERDUE_RETURN = "overdue_return", "Overdue return"
        HANDOVER_PENDING = "handover_pending", "Handover awaiting signature"
        NEW_RECEIPT = "new_receipt", "New goods receipt"
        LOW_STOCK = "low_stock", "Low stock"
        STATUS_CHANGE = "status_change", "Status change"
        CUSTOM_DATE = "custom_date", "Custom date column"
        MANUAL = "manual", "Manual (send now only)"

    section = models.ForeignKey(
        "navigation.SidebarItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="reminder_rules"
    )
    name = models.CharField(max_length=120)
    trigger = models.CharField(max_length=32, choices=Trigger.choices)
    trigger_config = models.JSONField(default=dict, blank=True)
    channels = models.JSONField(default=list, help_text='Subset of ["email", "sms", "in_app"]')
    recipients = models.JSONField(
        default=dict, help_text="{types:[holder|department_head|managers|users|custom], user_ids, emails, phones}"
    )
    schedule = models.JSONField(default=dict, help_text="{kind: daily|weekly|once|manual, time: HH:MM, timezone, weekday, date}")
    template = models.ForeignKey(ReminderTemplate, on_delete=models.PROTECT, related_name="rules")
    attachments = models.JSONField(
        default=list, blank=True, help_text='Subset of ["bill", "receipt_pdf", "export_csv", "export_xlsx", "export_pdf"]'
    )
    is_active = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ReminderLog(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    rule = models.ForeignKey(ReminderRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs")
    rule_name = models.CharField(max_length=120, blank=True)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    recipient_address = models.CharField(max_length=254, blank=True)
    channel = models.CharField(max_length=16, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField(blank=True)
    html = models.TextField(blank=True)
    object_ref = models.CharField(max_length=64, blank=True)
    link = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    attachments = models.JSONField(default=list, blank=True)
    dedupe_key = models.CharField(max_length=255, unique=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    is_test = models.BooleanField(default=False)
    deliver_after = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.channel} → {self.recipient_address} ({self.status})"


class NotificationPreference(models.Model):
    """Per-user opt-in/out per section (section=None is the user's default for all sections)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences")
    section = models.ForeignKey("navigation.SidebarItem", null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "section"], name="uniq_notification_pref", nulls_distinct=False)]

    def __str__(self):
        return f"{self.user_id} @ {self.section_id or 'all'}"


class ContactSettings(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contact_settings")
    verified_phone = models.CharField(max_length=32, blank=True)
    code_hash = models.CharField(max_length=128, blank=True)
    code_expires = models.DateTimeField(null=True, blank=True)
    code_attempts = models.PositiveSmallIntegerField(default=0)
    quiet_start = models.TimeField(null=True, blank=True)
    quiet_end = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")

    def __str__(self):
        return f"Contact settings for {self.user_id}"

    @property
    def phone_verified(self) -> bool:
        return bool(self.verified_phone) and self.verified_phone == (self.user.phone or "").strip()
