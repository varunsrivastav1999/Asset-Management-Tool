from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import TimeStampedModel


class MaintenanceRecord(TimeStampedModel):
    class Kind(models.TextChoices):
        PREVENTIVE = "preventive", "Preventive"
        CORRECTIVE = "corrective", "Repair"
        INSPECTION = "inspection", "Inspection"
        CALIBRATION = "calibration", "Calibration"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    asset = models.ForeignKey("assets.Asset", on_delete=models.CASCADE, related_name="maintenance_records")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.PREVENTIVE)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    scheduled_date = models.DateField(db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    vendor = models.ForeignKey("assets.Vendor", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    technician = models.CharField(max_length=160, blank=True)
    previous_asset_status = models.CharField(max_length=16, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.TextField(blank=True)
    custom_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-scheduled_date", "-id"]

    def __str__(self):
        return f"{self.asset_id} {self.title}"
