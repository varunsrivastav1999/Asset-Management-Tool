from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Category(models.TextChoices):
        WARRANTY = "warranty", "Warranty"
        MAINTENANCE = "maintenance", "Maintenance"
        HANDOVER = "handover", "Handover"
        RECEIVING = "receiving", "Receiving"
        ASSET = "asset", "Asset"
        SYSTEM = "system", "System"

    class Level(models.TextChoices):
        INFO = "info", "Info"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.SYSTEM, db_index=True)
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    link = models.CharField(max_length=255, blank=True)
    data = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=128, null=True, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["recipient", "is_read"])]
        constraints = [
            models.UniqueConstraint(fields=["recipient", "dedupe_key"], name="uniq_notification_dedupe"),
        ]

    def __str__(self):
        return f"{self.recipient_id}: {self.title}"
