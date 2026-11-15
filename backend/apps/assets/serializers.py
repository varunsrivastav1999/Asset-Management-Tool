import datetime

from django.db import transaction
from rest_framework import serializers

from apps.accounts.serializers import UserBriefSerializer
from apps.core.files import validate_image_upload

from .models import Asset, AssetEvent, AssetPhoto, Category, CustomField, Location, Vendor
from .services import clean_custom_data


class CustomFieldSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = CustomField
        fields = ["id", "key", "label", "field_type", "options", "required", "help_text", "order"]

    def validate(self, attrs):
        if attrs.get("field_type") == CustomField.FieldType.SELECT:
            options = attrs.get("options") or []
            if not isinstance(options, list) or not options or not all(isinstance(o, str) and o.strip() for o in options):
                raise serializers.ValidationError({"options": "Select fields need at least one text option."})
            attrs["options"] = [o.strip() for o in options]
        else:
            attrs["options"] = []
        return attrs


class CategorySerializer(serializers.ModelSerializer):
    custom_fields = CustomFieldSerializer(many=True, required=False)
    inherited_fields = serializers.SerializerMethodField()
    asset_count = serializers.IntegerField(read_only=True, default=0)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "parent",
            "parent_name",
            "icon",
            "color",
            "description",
            "is_active",
            "custom_fields",
            "inherited_fields",
            "asset_count",
            "created_at",
        ]
        read_only_fields = ["slug", "created_at"]

    def get_inherited_fields(self, obj) -> list[dict]:
        own = {f.key for f in obj.custom_fields.all()}
        return CustomFieldSerializer([f for f in obj.all_custom_fields() if f.key not in own], many=True).data

    def validate_parent(self, parent):
        if parent and self.instance:
            if parent.pk == self.instance.pk or parent.pk in self.instance.descendant_ids():
                raise serializers.ValidationError("A category cannot be nested under itself or its children.")
        return parent

    def validate_custom_fields(self, fields):
        keys = [f["key"] for f in fields]
        if len(keys) != len(set(keys)):
            raise serializers.ValidationError("Custom field keys must be unique within a category.")
        return fields

    @transaction.atomic
    def create(self, validated_data):
        fields = validated_data.pop("custom_fields", [])
        category = Category.objects.create(**validated_data)
        for f in fields:
            f.pop("id", None)
            CustomField.objects.create(category=category, **f)
        return category

    @transaction.atomic
    def update(self, instance, validated_data):
        fields = validated_data.pop("custom_fields", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if fields is not None:
            existing = {f.key: f for f in instance.custom_fields.all()}
            incoming = set()
            for f in fields:
                f.pop("id", None)
                incoming.add(f["key"])
                obj = existing.get(f["key"])
                if obj:
                    for k, v in f.items():
                        setattr(obj, k, v)
                    obj.save()
                else:
                    CustomField.objects.create(category=instance, **f)
            instance.custom_fields.exclude(key__in=incoming).delete()
        return instance


class LocationSerializer(serializers.ModelSerializer):
    asset_count = serializers.IntegerField(read_only=True, default=0)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)

    class Meta:
        model = Location
        fields = ["id", "name", "code", "parent", "parent_name", "address", "is_active", "asset_count", "created_at"]
        read_only_fields = ["created_at"]

    def validate_code(self, value):
        return value.strip().upper()

    def validate_parent(self, parent):
        if parent and self.instance:
            node, seen = parent, set()
            while node is not None and node.pk not in seen:
                if node.pk == self.instance.pk:
                    raise serializers.ValidationError("A location cannot be nested under itself.")
                seen.add(node.pk)
                node = node.parent
        return parent


class VendorSerializer(serializers.ModelSerializer):
    asset_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Vendor
        fields = [
            "id",
            "name",
            "contact_name",
            "email",
            "phone",
            "website",
            "address",
            "notes",
            "is_active",
            "asset_count",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class AssetPhotoSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(validators=[validate_image_upload])

    class Meta:
        model = AssetPhoto
        fields = ["id", "image", "caption", "is_primary", "created_at"]
        read_only_fields = ["created_at"]


class CategoryRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "icon", "color"]


class AssetListSerializer(serializers.ModelSerializer):
    category = CategoryRefSerializer(read_only=True)
    assigned_to = UserBriefSerializer(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    location_name = serializers.CharField(source="location.name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    thumbnail = serializers.SerializerMethodField()
    warranty_days_left = serializers.SerializerMethodField()
    received_date = serializers.SerializerMethodField()
    received_date_by = serializers.SerializerMethodField()

    class Meta:
        model = Asset
        fields = [
            "id",
            "asset_tag",
            "name",
            "category",
            "status",
            "status_display",
            "condition",
            "serial_number",
            "model",
            "manufacturer",
            "assigned_to",
            "department",
            "department_name",
            "location",
            "location_name",
            "purchase_cost",
            "currency",
            "warranty_expiry",
            "warranty_days_left",
            "next_maintenance_date",
            "thumbnail",
            "received_date",
            "received_date_by",
            "custom_data",
            "updated_at",
        ]

    def get_thumbnail(self, obj) -> str | None:
        photos = list(obj.photos.all())  # prefetched
        if not photos:
            return None
        request = self.context.get("request")
        url = photos[0].image.url
        return request.build_absolute_uri(url) if request else url

    def get_received_date(self, obj) -> str | None:
        d = obj.receipt.received_date if obj.receipt_id else obj.purchase_date
        return d.isoformat() if d else None

    def get_received_date_by(self, obj) -> str | None:
        if obj.receipt_id and obj.receipt.received_by:
            return obj.receipt.received_by.get_full_name() or obj.receipt.received_by.email
        return None

    def get_warranty_days_left(self, obj) -> int | None:
        if not obj.warranty_expiry:
            return None
        return (obj.warranty_expiry - datetime.date.today()).days


class AssetDetailSerializer(AssetListSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default=None)
    receipt_reference = serializers.CharField(source="receipt.reference", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True, default=None)
    photos = AssetPhotoSerializer(many=True, read_only=True)
    custom_fields = serializers.SerializerMethodField()
    qr_payload = serializers.CharField(read_only=True)
    condition_display = serializers.CharField(source="get_condition_display", read_only=True)
    has_invoice = serializers.SerializerMethodField()

    def get_has_invoice(self, obj) -> bool:
        return bool(obj.invoice_file)

    class Meta(AssetListSerializer.Meta):
        fields = AssetListSerializer.Meta.fields + [
            "description",
            "condition_display",
            "vendor",
            "vendor_name",
            "receipt",
            "receipt_reference",
            "purchase_date",
            "invoice_number",
            "po_number",
            "maintenance_interval_days",
            "assigned_at",
            "custom_fields",
            "notes",
            "photos",
            "qr_payload",
            "has_invoice",
            "created_by_name",
            "created_at",
        ]

    def get_custom_fields(self, obj) -> list[dict]:
        return CustomFieldSerializer(obj.category.all_custom_fields(), many=True).data


class AssetWriteSerializer(serializers.ModelSerializer):
    INITIAL_STATUSES = [Asset.Status.IN_STOCK, Asset.Status.IN_REPAIR, Asset.Status.LOST, Asset.Status.RETIRED]

    status = serializers.ChoiceField(choices=INITIAL_STATUSES, required=False)

    class Meta:
        model = Asset
        fields = [
            "id",
            "asset_tag",
            "name",
            "description",
            "category",
            "status",
            "condition",
            "serial_number",
            "model",
            "manufacturer",
            "vendor",
            "purchase_date",
            "purchase_cost",
            "currency",
            "invoice_number",
            "po_number",
            "warranty_expiry",
            "maintenance_interval_days",
            "next_maintenance_date",
            "location",
            "custom_data",
            "notes",
        ]
        read_only_fields = ["id", "asset_tag"]
        extra_kwargs = {"serial_number": {"allow_null": True, "required": False}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            # Status changes go through the change-status endpoint and workflows only.
            self.fields["status"].read_only = True

    def validate_serial_number(self, value):
        value = (value or "").strip()
        return value or None

    def validate_currency(self, value):
        value = (value or "USD").strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use a 3-letter ISO currency code.")
        return value

    def validate_category(self, category):
        if not category.is_active and (not self.instance or self.instance.category_id != category.pk):
            raise serializers.ValidationError("This category is inactive.")
        return category

    def validate(self, attrs):
        category = attrs.get("category") or getattr(self.instance, "category", None)
        if category is not None and ("custom_data" in attrs or "category" in attrs or self.instance is None):
            existing = getattr(self.instance, "custom_data", {}) if "custom_data" not in attrs else None
            cleaned = clean_custom_data(category, attrs.get("custom_data"), partial_existing=existing)
            # Keep values owned by custom table columns (keys that aren't category fields).
            category_keys = {f.key for f in category.all_custom_fields()}
            previous = getattr(self.instance, "custom_data", None) or {}
            attrs["custom_data"] = {**{k: v for k, v in previous.items() if k not in category_keys}, **cleaned}
        purchase = attrs.get("purchase_date", getattr(self.instance, "purchase_date", None))
        warranty = attrs.get("warranty_expiry", getattr(self.instance, "warranty_expiry", None))
        if purchase and warranty and warranty < purchase:
            raise serializers.ValidationError({"warranty_expiry": "Warranty cannot expire before the purchase date."})
        if purchase and purchase > datetime.date.today():
            raise serializers.ValidationError({"purchase_date": "Purchase date cannot be in the future."})
        interval = attrs.get("maintenance_interval_days", getattr(self.instance, "maintenance_interval_days", None))
        next_due = attrs.get("next_maintenance_date", getattr(self.instance, "next_maintenance_date", None))
        if interval and not next_due:
            attrs["next_maintenance_date"] = datetime.date.today() + datetime.timedelta(days=interval)
        return attrs


class AssetEventSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_event_type_display", read_only=True)
    actor_name = serializers.SerializerMethodField()
    from_user_name = serializers.SerializerMethodField()
    to_user_name = serializers.SerializerMethodField()
    from_department_name = serializers.CharField(source="from_department.name", default=None)
    to_department_name = serializers.CharField(source="to_department.name", default=None)
    from_location_name = serializers.CharField(source="from_location.name", default=None)
    to_location_name = serializers.CharField(source="to_location.name", default=None)
    handover_reference = serializers.CharField(source="handover.reference", default=None)
    receipt_reference = serializers.CharField(source="receipt.reference", default=None)

    class Meta:
        model = AssetEvent
        fields = [
            "id",
            "event_type",
            "label",
            "from_status",
            "to_status",
            "actor",
            "actor_name",
            "from_user",
            "from_user_name",
            "to_user",
            "to_user_name",
            "from_department_name",
            "to_department_name",
            "from_location_name",
            "to_location_name",
            "handover",
            "handover_reference",
            "receipt",
            "receipt_reference",
            "maintenance",
            "notes",
            "metadata",
            "created_at",
        ]

    @staticmethod
    def _name(user):
        return user.get_full_name() or user.email if user else None

    def get_actor_name(self, obj) -> str | None:
        return self._name(obj.actor) or "System"

    def get_from_user_name(self, obj) -> str | None:
        return self._name(obj.from_user)

    def get_to_user_name(self, obj) -> str | None:
        return self._name(obj.to_user)


class ChangeStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Asset.Status.choices)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class BulkUpdateSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, max_length=500)
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all(), required=False, allow_null=True)
    condition = serializers.ChoiceField(choices=Asset.Condition.choices, required=False)
    vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all(), required=False, allow_null=True)

    def validate(self, attrs):
        if len(attrs) < 2:
            raise serializers.ValidationError("Provide at least one field to update.")
        return attrs


class LabelsSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, max_length=300)
