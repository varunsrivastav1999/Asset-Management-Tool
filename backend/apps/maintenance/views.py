import django_filters
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.assets.filters import CharInFilter
from apps.assets.models import Asset, AssetEvent
from apps.assets.services import log_event
from apps.audit.services import AuditedViewSetMixin
from apps.core.permissions import IsManager
from apps.navigation.table_api import ConfigurableTableMixin

from . import services
from .models import MaintenanceRecord


class MaintenanceSerializer(serializers.ModelSerializer):
    asset_tag = serializers.CharField(source="asset.asset_tag", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    asset_status = serializers.CharField(source="asset.status", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True, default=None)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True, default=None)

    class Meta:
        model = MaintenanceRecord
        fields = [
            "id",
            "asset",
            "asset_tag",
            "asset_name",
            "asset_status",
            "kind",
            "kind_display",
            "title",
            "description",
            "status",
            "status_display",
            "scheduled_date",
            "started_at",
            "completed_date",
            "cost",
            "vendor",
            "vendor_name",
            "technician",
            "notes",
            "custom_data",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["status", "started_at", "completed_date", "created_at", "custom_data"]

    def validate_asset(self, asset):
        if asset.status == Asset.Status.RETIRED:
            raise serializers.ValidationError("Retired assets cannot be scheduled for maintenance.")
        return asset


class CompleteSerializer(serializers.Serializer):
    cost = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    completed_date = serializers.DateField(required=False, allow_null=True)
    condition = serializers.ChoiceField(choices=Asset.Condition.choices, required=False, allow_null=True)


class MaintenanceFilter(django_filters.FilterSet):
    status = CharInFilter(field_name="status", lookup_expr="in")
    scheduled_after = django_filters.DateFilter(field_name="scheduled_date", lookup_expr="gte")
    scheduled_before = django_filters.DateFilter(field_name="scheduled_date", lookup_expr="lte")

    class Meta:
        model = MaintenanceRecord
        fields = ["asset", "kind", "vendor"]


class MaintenanceViewSet(ConfigurableTableMixin, AuditedViewSetMixin, viewsets.ModelViewSet):
    table_key = "maintenance"

    def bulk_delete_reason(self, obj):
        return "In progress — complete or cancel it first." if obj.status == MaintenanceRecord.Status.IN_PROGRESS else None

    serializer_class = MaintenanceSerializer
    permission_classes = [IsManager]
    filterset_class = MaintenanceFilter
    search_fields = ["title", "description", "technician", "asset__asset_tag", "asset__name"]
    ordering_fields = ["scheduled_date", "completed_date", "cost", "created_at"]

    def get_queryset(self):
        return MaintenanceRecord.objects.select_related("asset", "vendor", "created_by")

    def get_save_kwargs(self, created):
        return {"created_by": self.request.user} if created else {}

    def perform_create(self, serializer):
        rec = super().perform_create(serializer)
        log_event(
            rec.asset,
            AssetEvent.Type.MAINTENANCE_SCHEDULED,
            self.request.user,
            maintenance=rec,
            notes=f"{rec.title} on {rec.scheduled_date:%Y-%m-%d}",
        )

    def perform_update(self, serializer):
        if serializer.instance.status not in (MaintenanceRecord.Status.SCHEDULED, MaintenanceRecord.Status.IN_PROGRESS):
            raise serializers.ValidationError({"detail": "Closed maintenance records cannot be edited."})
        if "asset" in serializer.validated_data and serializer.validated_data["asset"] != serializer.instance.asset:
            raise serializers.ValidationError({"asset": "The asset of an existing record cannot be changed."})
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.status == MaintenanceRecord.Status.IN_PROGRESS:
            raise serializers.ValidationError({"detail": "Complete or cancel in-progress maintenance first."})
        super().perform_destroy(instance)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        rec = services.start(self.get_object(), request.user)
        return Response(self.get_serializer(self.get_queryset().get(pk=rec.pk)).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        s = CompleteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rec = services.complete(self.get_object(), request.user, **s.validated_data)
        return Response(self.get_serializer(self.get_queryset().get(pk=rec.pk)).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        rec = services.cancel(self.get_object(), request.user)
        return Response(self.get_serializer(self.get_queryset().get(pk=rec.pk)).data)
