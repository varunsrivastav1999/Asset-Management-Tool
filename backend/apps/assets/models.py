from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify

from apps.core.files import asset_photo_path, invoice_path, private_storage
from apps.core.models import TimeStampedModel, next_reference


class Category(TimeStampedModel):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    icon = models.CharField(max_length=48, blank=True, default="box")
    color = models.CharField(max_length=16, blank=True, default="#10b981")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="uniq_category_name_per_parent", nulls_distinct=False)
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:120] or "category"
            slug, i = base, 2
            while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, i = f"{base}-{i}", i + 1
            self.slug = slug
        super().save(*args, **kwargs)

    def ancestors(self):
        chain, node, seen = [], self.parent, {self.pk}
        while node is not None and node.pk not in seen:
            chain.append(node)
            seen.add(node.pk)
            node = node.parent
        return chain

    def descendant_ids(self) -> list[int]:
        ids, frontier = [self.pk], [self.pk]
        while frontier:
            frontier = list(Category.objects.filter(parent_id__in=frontier).values_list("id", flat=True))
            frontier = [i for i in frontier if i not in ids]
            ids.extend(frontier)
        return ids

    def all_custom_fields(self):
        """Fields defined on this category and inherited from its ancestors (child overrides by key)."""
        fields = {}
        for cat in [*reversed(self.ancestors()), self]:
            for f in cat.custom_fields.all():
                fields[f.key] = f
        return sorted(fields.values(), key=lambda f: (f.order, f.label))


class CustomField(models.Model):
    class FieldType(models.TextChoices):
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        BOOLEAN = "boolean", "Yes / No"
        SELECT = "select", "Select"

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="custom_fields")
    key = models.SlugField(max_length=64)
    label = models.CharField(max_length=120)
    field_type = models.CharField(max_length=16, choices=FieldType.choices, default=FieldType.TEXT)
    options = models.JSONField(default=list, blank=True, help_text="Choices for select fields")
    required = models.BooleanField(default=False)
    help_text = models.CharField(max_length=255, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "label"]
        constraints = [models.UniqueConstraint(fields=["category", "key"], name="uniq_custom_field_key")]

    def __str__(self):
        return f"{self.category}: {self.label}"


class Location(TimeStampedModel):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=32, unique=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Vendor(TimeStampedModel):
    name = models.CharField(max_length=160, unique=True)
    contact_name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    website = models.URLField(blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Asset(TimeStampedModel):
    class Status(models.TextChoices):
        IN_STOCK = "in_stock", "In stock"
        ASSIGNED = "assigned", "Assigned"
        IN_REPAIR = "in_repair", "In repair"
        RETIRED = "retired", "Retired"
        LOST = "lost", "Lost"

    class Condition(models.TextChoices):
        NEW = "new", "New"
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        POOR = "poor", "Poor"
        DAMAGED = "damaged", "Damaged"

    asset_tag = models.CharField(max_length=32, unique=True, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="assets")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_STOCK, db_index=True)
    condition = models.CharField(max_length=16, choices=Condition.choices, default=Condition.NEW)

    serial_number = models.CharField(max_length=120, unique=True, null=True, blank=True)
    model = models.CharField(max_length=120, blank=True)
    manufacturer = models.CharField(max_length=120, blank=True)

    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    receipt = models.ForeignKey("workflows.GoodsReceipt", null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="USD")
    invoice_number = models.CharField(max_length=64, blank=True)
    po_number = models.CharField(max_length=64, blank=True)
    warranty_expiry = models.DateField(null=True, blank=True, db_index=True)
    invoice_file = models.FileField(
        upload_to=invoice_path, storage=private_storage, null=True, blank=True, help_text="Bill / invoice"
    )

    maintenance_interval_days = models.PositiveIntegerField(null=True, blank=True)
    next_maintenance_date = models.DateField(null=True, blank=True, db_index=True)

    location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="assets")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="assigned_assets"
    )
    department = models.ForeignKey("accounts.Department", null=True, blank=True, on_delete=models.PROTECT, related_name="assets")
    assigned_at = models.DateTimeField(null=True, blank=True)

    custom_data = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["category", "status"]),
        ]

    def __str__(self):
        return f"{self.asset_tag} · {self.name}"

    def save(self, *args, **kwargs):
        if not self.asset_tag:
            self.asset_tag = next_reference("AST")
        if self.serial_number is not None:
            self.serial_number = self.serial_number.strip() or None
        super().save(*args, **kwargs)

    @property
    def has_holder(self) -> bool:
        return bool(self.assigned_to_id or self.department_id)

    @property
    def qr_payload(self) -> str:
        return f"{settings.FRONTEND_URL}/a/{self.asset_tag}"


class AssetPhoto(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to=asset_photo_path)
    caption = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "created_at"]

    def __str__(self):
        return f"Photo of {self.asset_id}"


class AssetEvent(models.Model):
    """Immutable history log for an asset."""

    class Type(models.TextChoices):
        CREATED = "created", "Created"
        UPDATED = "updated", "Updated"
        RECEIVED = "received", "Received"
        ISSUED = "issued", "Issued"
        RETURNED = "returned", "Returned"
        TRANSFERRED = "transferred", "Transferred"
        STATUS_CHANGED = "status_changed", "Status changed"
        MAINTENANCE_SCHEDULED = "maintenance_scheduled", "Maintenance scheduled"
        MAINTENANCE_STARTED = "maintenance_started", "Maintenance started"
        MAINTENANCE_COMPLETED = "maintenance_completed", "Maintenance completed"
        PHOTO_ADDED = "photo_added", "Photo added"
        IMPORTED = "imported", "Imported"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=32, choices=Type.choices, db_index=True)
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16, blank=True)
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    from_department = models.ForeignKey("accounts.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    to_department = models.ForeignKey("accounts.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    from_location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    to_location = models.ForeignKey(Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    handover = models.ForeignKey("workflows.Handover", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    receipt = models.ForeignKey("workflows.GoodsReceipt", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    maintenance = models.ForeignKey(
        "maintenance.MaintenanceRecord", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.asset_id} {self.event_type}"
