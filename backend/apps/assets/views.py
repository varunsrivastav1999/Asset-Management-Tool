from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import AuditedViewSetMixin, diff, record, snapshot
from apps.core import codes
from apps.core.exceptions import DomainError
from apps.core.invoices import InvoiceFileMixin
from apps.core.pdf import Label, labels_pdf
from apps.core.permissions import IsManager, ReadAnyWriteManager, is_manager
from apps.core.responses import file_response as _file_response
from apps.navigation.table_api import ConfigurableTableMixin

from . import importexport
from .filters import AssetFilter
from .models import Asset, AssetEvent, AssetPhoto, Category, Location, Vendor
from .serializers import (
    AssetDetailSerializer,
    AssetEventSerializer,
    AssetListSerializer,
    AssetPhotoSerializer,
    AssetWriteSerializer,
    BulkUpdateSerializer,
    CategorySerializer,
    ChangeStatusSerializer,
    LabelsSerializer,
    LocationSerializer,
    VendorSerializer,
)
from .services import change_status, log_event


def asset_label(asset) -> Label:
    return Label(
        code=asset.asset_tag,
        title=asset.name,
        detail=f"S/N {asset.serial_number[:22]}" if asset.serial_number else "",
        qr_payload=asset.qr_payload,
    )


class CategoryViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [ReadAnyWriteManager]
    filterset_fields = ["parent", "is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]
    pagination_class = None

    def get_queryset(self):
        return (
            Category.objects.select_related("parent")
            .prefetch_related("custom_fields", "parent__custom_fields")
            .annotate(asset_count=Count("assets", distinct=True))
            .order_by("name")
        )


class LocationViewSet(ConfigurableTableMixin, AuditedViewSetMixin, viewsets.ModelViewSet):
    table_key = "locations"

    def bulk_delete_reason(self, obj):
        if obj.assets.exists():
            return "Still has assets."
        if obj.children.exists():
            return "Contains other locations."
        return None

    serializer_class = LocationSerializer
    permission_classes = [ReadAnyWriteManager]
    filterset_fields = ["parent", "is_active"]
    search_fields = ["name", "code", "address"]
    ordering_fields = ["name", "code", "created_at"]

    def get_queryset(self):
        return Location.objects.select_related("parent").annotate(asset_count=Count("assets", distinct=True)).order_by("name")


class VendorViewSet(ConfigurableTableMixin, AuditedViewSetMixin, viewsets.ModelViewSet):
    table_key = "vendors"

    def bulk_delete_reason(self, obj):
        return "Still linked to assets." if obj.assets.exists() else None

    serializer_class = VendorSerializer
    permission_classes = [ReadAnyWriteManager]
    filterset_fields = ["is_active"]
    search_fields = ["name", "contact_name", "email", "phone"]
    ordering_fields = ["name", "created_at"]

    def get_queryset(self):
        return Vendor.objects.annotate(asset_count=Count("assets", distinct=True)).order_by("name")


class AssetViewSet(InvoiceFileMixin, ConfigurableTableMixin, AuditedViewSetMixin, viewsets.ModelViewSet):
    table_key = "assets"

    def bulk_delete_reason(self, obj):
        if obj.has_holder:
            return "Assigned — return it before deleting."
        if obj.handover_items.exists():
            return "Has handover history — retire it instead."
        if obj.maintenance_records.exists():
            return "Has maintenance history — retire it instead."
        return None

    @extend_schema(request=dict, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="bulk-status", permission_classes=[IsManager])
    def bulk_status(self, request):
        """Change the status of many assets; invalid transitions are skipped with the reason."""
        from .services import status_change_error

        target = (request.data or {}).get("status")
        if target not in Asset.Status.values:
            raise DomainError("Choose a valid status.", field="status")
        notes = str((request.data or {}).get("notes", ""))[:2000]
        changed, skipped = [], []
        with transaction.atomic():
            for asset in self.bulk_queryset(request):
                reason = status_change_error(asset, target)
                if reason:
                    skipped.append({"id": asset.pk, "label": str(asset), "reason": reason})
                    continue
                change_status(asset, target, request.user, notes)
                changed.append(asset.pk)
        return Response({"updated": len(changed), "updated_ids": changed, "skipped": skipped})

    queryset = Asset.objects.none()
    permission_classes = [ReadAnyWriteManager]
    filterset_class = AssetFilter
    search_fields = [
        "asset_tag",
        "name",
        "serial_number",
        "model",
        "manufacturer",
        "invoice_number",
        "assigned_to__email",
        "assigned_to__first_name",
        "assigned_to__last_name",
    ]
    ordering_fields = [
        "asset_tag",
        "name",
        "status",
        "purchase_date",
        "purchase_cost",
        "warranty_expiry",
        "next_maintenance_date",
        "created_at",
        "updated_at",
    ]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = Asset.objects.select_related(
            "category",
            "category__parent",
            "assigned_to",
            "department",
            "location",
            "vendor",
            "receipt",
            "receipt__received_by",
            "created_by",
        ).prefetch_related(
            Prefetch("photos", queryset=AssetPhoto.objects.order_by("-is_primary", "created_at")),
            "category__custom_fields",
            "category__parent__custom_fields",
        )
        user = self.request.user
        if not is_manager(user):
            qs = qs.filter(assigned_to=user)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return AssetListSerializer
        if self.action in ("create", "update", "partial_update"):
            return AssetWriteSerializer
        return AssetDetailSerializer

    def get_save_kwargs(self, created):
        return {"created_by": self.request.user} if created else {}

    def perform_create(self, serializer):
        asset = super().perform_create(serializer)
        log_event(asset, AssetEvent.Type.CREATED, self.request.user, to_status=asset.status, to_location=asset.location)

    def perform_update(self, serializer):
        before = snapshot(serializer.instance)
        asset = super().perform_update(serializer)
        changes = diff(before, snapshot(asset))
        if changes:
            log_event(asset, AssetEvent.Type.UPDATED, self.request.user, metadata={"fields": sorted(changes)})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        out = AssetDetailSerializer(serializer.instance, context=self.get_serializer_context())
        return Response(out.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        instance.refresh_from_db()
        return Response(
            AssetDetailSerializer(self.get_queryset().get(pk=instance.pk), context=self.get_serializer_context()).data
        )

    def perform_destroy(self, instance):
        if instance.has_holder:
            raise DomainError("Return the asset before deleting it.")
        super().perform_destroy(instance)

    # --- history & codes --------------------------------------------------
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        asset = self.get_object()
        events = asset.events.select_related(
            "actor",
            "from_user",
            "to_user",
            "from_department",
            "to_department",
            "from_location",
            "to_location",
            "handover",
            "receipt",
        )
        page = self.paginate_queryset(events)
        return self.get_paginated_response(AssetEventSerializer(page, many=True).data)

    @extend_schema(parameters=[OpenApiParameter("fmt", str, enum=["png", "svg"])])
    @action(detail=True, methods=["get"])
    def qr(self, request, pk=None):
        asset = self.get_object()
        if request.query_params.get("fmt") == "svg":
            return _file_response(codes.qr_svg(asset.qr_payload), "image/svg+xml", f"{asset.asset_tag}-qr.svg", inline=True)
        return _file_response(codes.qr_png(asset.qr_payload), "image/png", f"{asset.asset_tag}-qr.png", inline=True)

    @action(detail=True, methods=["get"])
    def barcode(self, request, pk=None):
        asset = self.get_object()
        if request.query_params.get("fmt") == "png":
            return _file_response(codes.barcode_png(asset.asset_tag), "image/png", f"{asset.asset_tag}-barcode.png", inline=True)
        return _file_response(codes.barcode_svg(asset.asset_tag), "image/svg+xml", f"{asset.asset_tag}-barcode.svg", inline=True)

    @extend_schema(parameters=[OpenApiParameter("code", str, required=True)])
    @action(detail=False, methods=["get"])
    def lookup(self, request):
        """Resolve a scanned QR / barcode (asset tag, serial number or asset URL) to an asset."""
        code = (request.query_params.get("code") or "").strip()
        if not code:
            raise DomainError("Provide a code to look up.", field="code")
        if "/a/" in code:
            code = code.rstrip("/").rsplit("/a/", 1)[-1]
        asset = self.get_queryset().filter(Q(asset_tag__iexact=code) | Q(serial_number__iexact=code)).first()
        if asset is None:
            return Response({"detail": "No asset matches this code."}, status=status.HTTP_404_NOT_FOUND)
        return Response(AssetDetailSerializer(asset, context=self.get_serializer_context()).data)

    # --- status -----------------------------------------------------------
    @extend_schema(request=ChangeStatusSerializer, responses=AssetDetailSerializer)
    @action(detail=True, methods=["post"], url_path="change-status", permission_classes=[IsManager])
    def change_status(self, request, pk=None):
        asset = self.get_object()
        serializer = ChangeStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        change_status(asset, serializer.validated_data["status"], request.user, serializer.validated_data.get("notes", ""))
        return Response(AssetDetailSerializer(self.get_queryset().get(pk=asset.pk), context=self.get_serializer_context()).data)

    # --- photos -----------------------------------------------------------
    @extend_schema(request=AssetPhotoSerializer, responses=AssetPhotoSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsManager], parser_classes=[MultiPartParser, FormParser])
    def photos(self, request, pk=None):
        asset = self.get_object()
        if AssetPhoto.objects.filter(asset=asset).count() >= 12:
            raise DomainError("An asset can have at most 12 photos.")
        serializer = AssetPhotoSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            make_primary = serializer.validated_data.get("is_primary") or not AssetPhoto.objects.filter(asset=asset).exists()
            if make_primary:
                asset.photos.update(is_primary=False)
            photo = serializer.save(asset=asset, uploaded_by=request.user, is_primary=make_primary)
            log_event(asset, AssetEvent.Type.PHOTO_ADDED, request.user)
        return Response(AssetPhotoSerializer(photo, context=self.get_serializer_context()).data, status=201)

    @action(
        detail=True,
        methods=["delete", "patch"],
        url_path=r"photos/(?P<photo_id>\d+)",
        permission_classes=[IsManager],
    )
    def photo_detail(self, request, pk=None, photo_id=None):
        asset = self.get_object()
        photo = get_object_or_404(asset.photos, pk=photo_id)
        if request.method == "DELETE":
            was_primary = photo.is_primary
            photo.image.delete(save=False)
            photo.delete()
            if was_primary:
                nxt = AssetPhoto.objects.filter(asset=asset).order_by("created_at").first()
                if nxt:
                    nxt.is_primary = True
                    nxt.save(update_fields=["is_primary"])
            return Response(status=status.HTTP_204_NO_CONTENT)
        with transaction.atomic():
            if request.data.get("is_primary") in (True, "true", "1"):
                asset.photos.update(is_primary=False)
                photo.is_primary = True
            if "caption" in request.data:
                photo.caption = str(request.data["caption"])[:200]
            photo.save()
        return Response(AssetPhotoSerializer(photo, context=self.get_serializer_context()).data)

    # --- bulk -------------------------------------------------------------
    @extend_schema(request=BulkUpdateSerializer)
    @action(detail=False, methods=["post"], url_path="bulk-update", permission_classes=[IsManager])
    def bulk_update(self, request):
        serializer = BulkUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        ids = data.pop("ids")
        with transaction.atomic():
            qs = Asset.objects.select_for_update(of=("self",)).filter(pk__in=ids)
            assets = list(qs)
            updated = qs.update(**data, updated_at=timezone.now())
            for asset in assets:
                log_event(asset, AssetEvent.Type.UPDATED, request.user, metadata={"bulk": True, "fields": sorted(data)})
        record(
            AuditLog.Action.BULK_UPDATE,
            request.user,
            model="assets.asset",
            object_repr=f"{updated} assets",
            changes={"ids": ids, "fields": {k: getattr(v, "pk", v) for k, v in data.items()}},
        )
        return Response({"updated": updated})

    @extend_schema(request=LabelsSerializer, responses={(200, "application/pdf"): bytes})
    @action(detail=False, methods=["post"], permission_classes=[IsManager])
    def labels(self, request):
        serializer = LabelsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assets = list(Asset.objects.filter(pk__in=serializer.validated_data["ids"]).order_by("asset_tag"))
        if not assets:
            raise DomainError("No matching assets.")
        return _file_response(labels_pdf([asset_label(a) for a in assets]), "application/pdf", "asset-labels.pdf")

    # --- import / export --------------------------------------------------
    @extend_schema(parameters=[OpenApiParameter("file_format", str, enum=["csv", "xlsx"])])
    @action(detail=False, methods=["get"], permission_classes=[IsManager])
    def export(self, request):
        qs = (
            self.filter_queryset(self.get_queryset())
            .select_related(None)
            .select_related("category", "vendor", "location", "assigned_to", "department")
            .prefetch_related(None)
        )
        fmt = request.query_params.get("file_format", "xlsx")
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        count = qs.count()
        record(
            AuditLog.Action.EXPORT,
            request.user,
            model="assets.asset",
            object_repr=f"{count} assets ({fmt})",
            changes={"filters": {k: v for k, v in request.query_params.items()}},
        )
        if fmt == "csv":
            return _file_response(importexport.export_csv(qs), "text/csv; charset=utf-8", f"assets-{stamp}.csv")
        return _file_response(
            importexport.export_xlsx(qs),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"assets-{stamp}.xlsx",
        )

    @action(detail=False, methods=["get"], url_path="import-template", permission_classes=[IsManager])
    def import_template(self, request):
        return _file_response(
            importexport.template_xlsx(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "asset-import-template.xlsx",
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="import",
        permission_classes=[IsManager],
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_assets(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise DomainError("Attach a .csv or .xlsx file.", field="file")
        dry_run = str(request.data.get("dry_run", "false")).lower() in ("1", "true", "yes")
        report = importexport.import_assets(upload, request.user, dry_run=dry_run)
        if not dry_run and not report["errors"]:
            record(
                AuditLog.Action.IMPORT,
                request.user,
                model="assets.asset",
                object_repr=f"{report['created']} created / {report['updated']} updated",
                changes={"file": upload.name, "created": report["created"], "updated": report["updated"]},
            )
        code = status.HTTP_200_OK if not report["errors"] else status.HTTP_400_BAD_REQUEST
        return Response(report, status=code)


class MyAssetsViewSet(viewsets.ReadOnlyModelViewSet):
    """Assets currently held by the requesting user (all roles)."""

    queryset = Asset.objects.none()
    serializer_class = AssetListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Asset.objects.filter(assigned_to=self.request.user)
            .exclude(status=Asset.Status.RETIRED)
            .select_related("category", "assigned_to", "department", "location")
            .prefetch_related("photos")
        )
