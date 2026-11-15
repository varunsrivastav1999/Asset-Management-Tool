from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Department
from apps.accounts.serializers import UserBriefSerializer
from apps.assets.models import Asset, Category, Location
from apps.core.files import decode_signature

from .models import GoodsReceipt, Handover, HandoverItem

User = get_user_model()


class SignatureField(serializers.CharField):
    """Accepts a canvas data URL and returns a validated PNG ContentFile."""

    def to_internal_value(self, data):
        return decode_signature(super().to_internal_value(data))


# --- Receiving -----------------------------------------------------------------
class ReceiptItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.filter(is_active=True))
    quantity = serializers.IntegerField(min_value=1, max_value=500, default=1)
    serial_numbers = serializers.ListField(child=serializers.CharField(max_length=120), required=False, default=list)
    model = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    manufacturer = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    condition = serializers.ChoiceField(choices=Asset.Condition.choices, default=Asset.Condition.NEW)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True)
    currency = serializers.CharField(max_length=3, default="USD")
    warranty_expiry = serializers.DateField(required=False, allow_null=True)
    maintenance_interval_days = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    custom_data = serializers.DictField(required=False, default=dict)

    def validate(self, attrs):
        serials = [s.strip() for s in attrs.get("serial_numbers", []) if s and s.strip()]
        if len(serials) > attrs["quantity"]:
            raise serializers.ValidationError({"serial_numbers": "More serial numbers than quantity."})
        if len(serials) != len(set(serials)):
            raise serializers.ValidationError({"serial_numbers": "Serial numbers must be unique."})
        taken = list(Asset.objects.filter(serial_number__in=serials).values_list("serial_number", flat=True))
        if taken:
            raise serializers.ValidationError({"serial_numbers": f"Already registered: {', '.join(taken)}."})
        attrs["serial_numbers"] = serials
        attrs["currency"] = attrs["currency"].upper()
        return attrs


class GoodsReceiptSerializer(serializers.ModelSerializer):
    items = ReceiptItemSerializer(many=True, write_only=True)
    signature = SignatureField(write_only=True, required=False)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default=None)
    location_name = serializers.CharField(source="location.name", read_only=True, default=None)
    received_by_name = serializers.CharField(source="received_by.get_full_name", read_only=True, default=None)
    asset_count = serializers.IntegerField(read_only=True, default=0)
    total_value = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True, default=0)
    is_signed = serializers.SerializerMethodField()
    has_invoice = serializers.SerializerMethodField()

    def get_has_invoice(self, obj) -> bool:
        return bool(obj.invoice_file)

    class Meta:
        model = GoodsReceipt
        fields = [
            "id",
            "reference",
            "vendor",
            "vendor_name",
            "received_date",
            "invoice_number",
            "po_number",
            "location",
            "location_name",
            "received_by",
            "received_by_name",
            "notes",
            "signed_name",
            "signed_at",
            "is_signed",
            "has_invoice",
            "asset_count",
            "total_value",
            "custom_data",
            "items",
            "signature",
            "created_at",
        ]
        read_only_fields = ["reference", "received_by", "signed_at", "created_at", "custom_data"]

    def get_is_signed(self, obj) -> bool:
        return bool(obj.signature)

    def validate_received_date(self, value):
        if value > timezone.localdate():
            raise serializers.ValidationError("Received date cannot be in the future.")
        return value

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Add at least one item.")
        if sum(i["quantity"] for i in items) > 1000:
            raise serializers.ValidationError("At most 1000 assets per receipt.")
        serials = [s for i in items for s in i.get("serial_numbers", [])]
        if len(serials) != len(set(serials)):
            raise serializers.ValidationError("Serial numbers must be unique across items.")
        return items


# --- Handovers -----------------------------------------------------------------
class HandoverItemSerializer(serializers.ModelSerializer):
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.all())
    asset_tag = serializers.CharField(source="asset.asset_tag", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    serial_number = serializers.CharField(source="asset.serial_number", read_only=True, default=None)
    category_name = serializers.CharField(source="asset.category.name", read_only=True)
    condition = serializers.ChoiceField(choices=Asset.Condition.choices, required=False)

    class Meta:
        model = HandoverItem
        fields = ["id", "asset", "asset_tag", "asset_name", "serial_number", "category_name", "condition", "notes"]


class HandoverSerializer(serializers.ModelSerializer):
    items = HandoverItemSerializer(many=True)
    from_user_detail = UserBriefSerializer(source="from_user", read_only=True)
    to_user_detail = UserBriefSerializer(source="to_user", read_only=True)
    signer_detail = UserBriefSerializer(source="signer", read_only=True)
    from_department_name = serializers.CharField(source="from_department.name", read_only=True, default=None)
    to_department_name = serializers.CharField(source="to_department.name", read_only=True, default=None)
    to_location_name = serializers.CharField(source="to_location.name", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True, default=None)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    to_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    to_department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all(), required=False, allow_null=True)
    to_location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all(), required=False, allow_null=True)
    issuer_signature = SignatureField(write_only=True, required=False)
    signature = SignatureField(write_only=True, required=False)
    has_issuer_signature = serializers.SerializerMethodField()
    is_signed = serializers.SerializerMethodField()
    can_sign = serializers.SerializerMethodField()

    class Meta:
        model = Handover
        fields = [
            "id",
            "reference",
            "type",
            "type_display",
            "status",
            "status_display",
            "from_user",
            "from_user_detail",
            "from_department",
            "from_department_name",
            "to_user",
            "to_user_detail",
            "to_department",
            "to_department_name",
            "to_location",
            "to_location_name",
            "signer",
            "signer_detail",
            "created_by",
            "created_by_name",
            "expected_return_date",
            "notes",
            "items",
            "issuer_signature",
            "signature",
            "signed_name",
            "signed_at",
            "has_issuer_signature",
            "is_signed",
            "can_sign",
            "completed_at",
            "cancelled_at",
            "cancel_reason",
            "created_at",
        ]
        read_only_fields = [
            "reference",
            "status",
            "from_user",
            "from_department",
            "signer",
            "created_by",
            "signed_at",
            "completed_at",
            "cancelled_at",
            "cancel_reason",
            "created_at",
        ]

    def get_has_issuer_signature(self, obj) -> bool:
        return bool(obj.issuer_signature)

    def get_is_signed(self, obj) -> bool:
        return bool(obj.signature)

    def get_can_sign(self, obj) -> bool:
        from .services import can_sign

        request = self.context.get("request")
        return bool(request and can_sign(obj, request.user))

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("Select at least one asset.")
        if len(items) > 200:
            raise serializers.ValidationError("At most 200 assets per handover.")
        ids = [i["asset"].pk for i in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Each asset can appear only once.")
        return items

    def validate_expected_return_date(self, value):
        if value and value < timezone.localdate():
            raise serializers.ValidationError("Expected return date cannot be in the past.")
        return value


class HandoverListSerializer(serializers.ModelSerializer):
    from_name = serializers.SerializerMethodField()
    to_name = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True, default=0)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    signer_name = serializers.CharField(source="signer.get_full_name", read_only=True, default=None)

    class Meta:
        model = Handover
        fields = [
            "id",
            "reference",
            "type",
            "type_display",
            "status",
            "status_display",
            "from_name",
            "to_name",
            "signer",
            "signer_name",
            "item_count",
            "expected_return_date",
            "custom_data",
            "created_at",
            "completed_at",
        ]

    @staticmethod
    def _party(user, dept, fallback):
        if user:
            return user.get_full_name() or user.email
        return dept.name if dept else fallback

    def get_from_name(self, obj) -> str | None:
        return self._party(obj.from_user, obj.from_department, "Store")

    def get_to_name(self, obj) -> str | None:
        return self._party(obj.to_user, obj.to_department, "Store")


class SignSerializer(serializers.Serializer):
    signature = SignatureField()
    signed_name = serializers.CharField(max_length=160, required=False, allow_blank=True)


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
