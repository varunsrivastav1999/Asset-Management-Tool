from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.files import invoice_path, private_storage, signature_path
from apps.core.models import TimeStampedModel, next_reference


class GoodsReceipt(TimeStampedModel):
    """Inward receiving of new assets (GRN)."""

    reference = models.CharField(max_length=32, unique=True, editable=False)
    vendor = models.ForeignKey("assets.Vendor", null=True, blank=True, on_delete=models.SET_NULL, related_name="receipts")
    received_date = models.DateField(default=timezone.localdate)
    invoice_number = models.CharField(max_length=64, blank=True)
    po_number = models.CharField(max_length=64, blank=True)
    invoice_file = models.FileField(
        upload_to=invoice_path, storage=private_storage, null=True, blank=True, help_text="Bill / invoice"
    )
    location = models.ForeignKey("assets.Location", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    notes = models.TextField(blank=True)
    signature = models.ImageField(upload_to=signature_path, storage=private_storage, null=True, blank=True)
    signed_name = models.CharField(max_length=160, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    custom_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.reference

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = next_reference("GRN")
        super().save(*args, **kwargs)


class Handover(TimeStampedModel):
    class Type(models.TextChoices):
        ISSUE = "issue", "Issue"
        RETURN = "return", "Return"
        TRANSFER = "transfer", "Transfer"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending sign-off"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    reference = models.CharField(max_length=32, unique=True, editable=False)
    type = models.CharField(max_length=16, choices=Type.choices, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="handovers_from"
    )
    from_department = models.ForeignKey("accounts.Department", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="handovers_to"
    )
    to_department = models.ForeignKey("accounts.Department", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    to_location = models.ForeignKey("assets.Location", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    # The employee who must acknowledge; null means a manager signs in person.
    signer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="handovers_to_sign"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    expected_return_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    issuer_signature = models.ImageField(upload_to=signature_path, storage=private_storage, null=True, blank=True)
    signature = models.ImageField(upload_to=signature_path, storage=private_storage, null=True, blank=True)
    signed_name = models.CharField(max_length=160, blank=True)
    signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    signed_at = models.DateTimeField(null=True, blank=True)
    signed_ip = models.GenericIPAddressField(null=True, blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=500, blank=True)
    overdue_notified = models.BooleanField(default=False)
    custom_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "type"])]

    def __str__(self):
        return f"{self.reference} ({self.get_type_display()})"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = next_reference("HND")
        super().save(*args, **kwargs)


class HandoverItem(models.Model):
    handover = models.ForeignKey(Handover, on_delete=models.CASCADE, related_name="items")
    asset = models.ForeignKey("assets.Asset", on_delete=models.PROTECT, related_name="handover_items")
    condition = models.CharField(max_length=16, default="good")
    notes = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["handover", "asset"], name="uniq_handover_asset")]

    def __str__(self):
        return f"{self.handover_id}:{self.asset_id}"

    def get_condition_display(self):
        from apps.assets.models import Asset

        return dict(Asset.Condition.choices).get(self.condition, self.condition)
