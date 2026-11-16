import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

from apps.core.files import private_storage, upload_to
from apps.core.models import TimeStampedModel
from apps.core.roles import default_roles

HEX_COLOR = RegexValidator(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$", "Use a hex color such as #10b981.")


class SidebarItem(TimeStampedModel):
    class Type(models.TextChoices):
        PAGE = "page", "Page (in-app route)"
        LINK = "link", "External link"
        GROUP = "group", "Group"
        DIVIDER = "divider", "Divider"

    name = models.CharField(max_length=80, blank=True)
    item_type = models.CharField("type", max_length=16, choices=Type.choices, default=Type.PAGE)
    icon = models.CharField(max_length=48, blank=True)
    route = models.CharField(max_length=200, blank=True, help_text="In-app path for pages, e.g. /assets")
    url = models.URLField(max_length=500, blank=True, help_text="Absolute http(s) URL for links")
    open_in_new_tab = models.BooleanField(default=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    order = models.PositiveIntegerField(default=0, db_index=True)
    visible_roles = models.JSONField(default=default_roles)
    is_active = models.BooleanField(default=True)

    # Appearance (all optional; empty means "use the theme default").
    color = models.CharField(max_length=9, blank=True, validators=[HEX_COLOR], help_text="Label color")
    icon_color = models.CharField(max_length=9, blank=True, validators=[HEX_COLOR])
    active_color = models.CharField(max_length=9, blank=True, validators=[HEX_COLOR], help_text="Highlight when the page is open")
    gradient = models.BooleanField(default=False, help_text="Active highlight uses a gradient from active color to color")
    glow = models.BooleanField(default=False, help_text="Soft glow around the icon / active highlight")

    # Pages that render a data table point at a table definition (see navigation.tables).
    table = models.CharField(max_length=32, blank=True, help_text="Table definition key, e.g. 'assets'")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name or self.get_item_type_display()


class TableColumn(TimeStampedModel):
    """One column of a configurable table, scoped to a sidebar page."""

    class Type(models.TextChoices):
        AUTO_NUMBER = "auto_number", "Auto number (S.No)"
        TEXT = "text", "Text"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
        BOOLEAN = "boolean", "Yes / No"
        SELECT = "select", "Select"
        USER = "user", "User"
        STATUS = "status", "Status"
        FILE = "file", "File / link"
        MEDIA = "media", "Media (photo / file upload)"

    sidebar_item = models.ForeignKey(SidebarItem, on_delete=models.CASCADE, related_name="columns")
    name = models.CharField(max_length=60, help_text="Header label")
    key = models.SlugField(max_length=64)
    column_type = models.CharField("type", max_length=16, choices=Type.choices, default=Type.TEXT)
    options = models.JSONField(default=list, blank=True, help_text="Choices for select columns")
    width = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Width in pixels (optional)")
    order = models.PositiveIntegerField(default=0, db_index=True)
    is_visible = models.BooleanField(default=True, help_text="Shown by default (users may still toggle it)")
    is_required = models.BooleanField(default=False, help_text="Always shown; users cannot hide it")
    is_searchable = models.BooleanField(default=False)
    is_sortable = models.BooleanField(default=False)
    is_builtin = models.BooleanField(default=False, editable=False)
    visible_roles = models.JSONField(default=default_roles)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["sidebar_item", "key"], name="uniq_table_column_key")]

    def __str__(self):
        return f"{self.sidebar_item}: {self.name}"


class TablePreference(models.Model):
    """A user's personal show/hide choices for one table."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="table_preferences")
    sidebar_item = models.ForeignKey(SidebarItem, on_delete=models.CASCADE, related_name="preferences")
    hidden = models.JSONField(default=list, blank=True)
    shown = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "sidebar_item"], name="uniq_table_pref")]

    def __str__(self):
        return f"{self.user_id} @ {self.sidebar_item_id}"


class TableDefinition(TimeStampedModel):
    """The table a sidebar page shows: its names, icon and description, editable by admins.

    `source` is a built-in table key (assets, receipts, …) or "custom" for admin-created tables
    whose rows are TableRecords.
    """

    CUSTOM = "custom"

    sidebar_item = models.OneToOneField(SidebarItem, on_delete=models.CASCADE, related_name="definition")
    source = models.CharField(max_length=32, db_index=True)
    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=80, help_text="Plural display name, e.g. Equipment")
    singular = models.CharField(max_length=80, help_text="Used in buttons, e.g. Add Equipment item")
    icon = models.CharField(max_length=48, blank=True)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(Lower("name"), name="uniq_table_definition_name_ci")]

    def __str__(self):
        return self.name


def record_code(slug: str, pk: int) -> str:
    """Permanent row code shown on labels and encoded in QR / barcodes, e.g. "LIC-00012".

    The prefix comes from the table's address when the row is created; the number is the row's id, so codes are
    unique across all tables and never change (renaming the table or moving the row keeps the code).
    """
    letters = "".join(ch for ch in (slug or "") if ch.isalnum()).upper()
    return f"{letters[:3] or 'REC'}-{pk:05d}"


class TableRecord(TimeStampedModel):
    """A row of an admin-created (custom) table. Column values live in custom_data."""

    definition = models.ForeignKey(TableDefinition, null=True, blank=True, on_delete=models.SET_NULL, related_name="records")
    code = models.CharField(max_length=24, unique=True, null=True, blank=True, editable=False)
    custom_data = models.JSONField(default=dict, blank=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_from = models.CharField(max_length=80, blank=True, help_text="Table name when the table was deleted")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.code or f"Record {self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.code:  # needs the id, so it's set right after the first insert
            self.code = record_code(self.definition.slug if self.definition_id else "", self.pk)
            type(self).objects.filter(pk=self.pk).update(code=self.code)

    @property
    def title(self) -> str:
        """The row's first text value, for labels and lookups."""
        for value in (self.custom_data or {}).values():
            if isinstance(value, str) and value.strip():
                return value.strip()
        return self.code or ""


def table_media_path(instance, filename):
    return upload_to("table-media")(instance, filename)


class TableMedia(models.Model):
    """A photo or file uploaded into a Media column. Stored privately; served only to people who can see the page.

    The cell itself stores {"id", "name", "type", "size"}; files no cell points to are purged daily.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sidebar_item = models.ForeignKey(SidebarItem, on_delete=models.CASCADE, related_name="media")
    column_key = models.CharField(max_length=64)
    file = models.FileField(upload_to=table_media_path, storage=private_storage, max_length=255)
    name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["sidebar_item", "column_key"])]

    def __str__(self):
        return self.name

    @property
    def is_image(self) -> bool:
        return self.content_type.startswith("image/")

    def as_value(self) -> dict:
        return {"id": str(self.id), "name": self.name, "type": self.content_type, "size": self.size}
