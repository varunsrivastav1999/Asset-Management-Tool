from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.exceptions import DomainError
from apps.core.invoices import InvoiceFileMixin
from apps.core.middleware import client_ip
from apps.core.pdf import handover_pdf, receipt_pdf
from apps.core.permissions import IsManager, is_manager
from apps.navigation.table_api import ConfigurableTableMixin

from .models import GoodsReceipt, Handover
from .serializers import (
    CancelSerializer,
    GoodsReceiptSerializer,
    HandoverListSerializer,
    HandoverSerializer,
    SignSerializer,
)
from .services import can_sign, cancel_handover, complete_handover, create_handover, create_receipt


def _pdf(content, filename):
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


class GoodsReceiptViewSet(
    InvoiceFileMixin,
    ConfigurableTableMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    table_key = "receipts"

    def bulk_delete_reason(self, obj):
        n = obj.assets.count()
        return f"Has {n} received asset(s)." if n else None

    serializer_class = GoodsReceiptSerializer
    permission_classes = [IsManager]
    filterset_fields = ["vendor", "location", "received_date"]
    search_fields = ["reference", "invoice_number", "po_number", "vendor__name", "notes"]
    ordering_fields = ["received_date", "created_at", "reference"]

    def get_queryset(self):
        return (
            GoodsReceipt.objects.select_related("vendor", "location", "received_by")
            .annotate(asset_count=Count("assets", distinct=True), total_value=Sum("assets__purchase_cost"))
            .order_by("-created_at", "-id")
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        signature = data.pop("signature", None)
        receipt = create_receipt(data, request.user, signature_file=signature)
        out = self.get_serializer(self.get_queryset().get(pk=receipt.pk))
        return Response(out.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        receipt = self.get_object()
        return _pdf(receipt_pdf(receipt), f"{receipt.reference}.pdf")


class HandoverViewSet(
    ConfigurableTableMixin, mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    table_key = "handovers"

    def bulk_delete_reason(self, obj):
        if obj.status == Handover.Status.COMPLETED:
            return "Completed handovers are kept for the audit trail."
        if obj.status == Handover.Status.PENDING:
            return "Pending — cancel it first."
        return None

    queryset = Handover.objects.none()
    filterset_fields = ["type", "status", "to_user", "from_user", "to_department", "signer"]
    search_fields = [
        "reference",
        "notes",
        "to_user__email",
        "to_user__first_name",
        "to_user__last_name",
        "from_user__email",
        "from_user__first_name",
        "from_user__last_name",
        "items__asset__asset_tag",
    ]
    ordering_fields = ["created_at", "completed_at", "reference"]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ("create", "cancel"):
            return [IsManager()]
        return super().get_permissions()

    def get_queryset(self):
        qs = Handover.objects.select_related(
            "from_user", "to_user", "from_department", "to_department", "to_location", "signer", "created_by"
        )
        user = self.request.user
        if not is_manager(user):
            qs = qs.filter(Q(to_user=user) | Q(from_user=user) | Q(signer=user))
        if self.action == "list":
            qs = qs.annotate(item_count=Count("items")).order_by("-created_at", "-id")
            if self.request.query_params.get("awaiting_me") in ("1", "true"):
                qs = qs.filter(status=Handover.Status.PENDING, signer=user)
        else:
            qs = qs.prefetch_related("items__asset__category")
        return qs.distinct() if not is_manager(user) else qs

    def get_serializer_class(self):
        return HandoverListSerializer if self.action == "list" else HandoverSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        issuer_sig = data.pop("issuer_signature", None)
        signature = data.pop("signature", None)
        signed_name = data.pop("signed_name", "")
        handover = create_handover(
            data, request.user, issuer_signature=issuer_sig, signature=signature, signed_name=signed_name, ip=client_ip(request)
        )
        out = HandoverSerializer(self.get_queryset().get(pk=handover.pk), context=self.get_serializer_context())
        return Response(out.data, status=status.HTTP_201_CREATED)

    @extend_schema(request=SignSerializer, responses=HandoverSerializer)
    @action(detail=True, methods=["post"])
    def sign(self, request, pk=None):
        handover = self.get_object()
        if not can_sign(handover, request.user):
            if handover.status != Handover.Status.PENDING:
                raise DomainError(f"Handover is already {handover.get_status_display().lower()}.")
            return Response({"detail": "You are not allowed to sign this handover."}, status=status.HTTP_403_FORBIDDEN)
        serializer = SignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        complete_handover(
            handover,
            serializer.validated_data["signature"],
            serializer.validated_data.get("signed_name", ""),
            request.user,
            ip=client_ip(request),
        )
        return Response(HandoverSerializer(self.get_queryset().get(pk=handover.pk), context=self.get_serializer_context()).data)

    @extend_schema(request=CancelSerializer, responses=HandoverSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        handover = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_handover(handover, request.user, serializer.validated_data["reason"])
        return Response(HandoverSerializer(self.get_queryset().get(pk=handover.pk), context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        handover = self.get_object()
        return _pdf(handover_pdf(handover), f"{handover.reference}.pdf")
