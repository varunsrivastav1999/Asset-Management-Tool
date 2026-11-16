import logging

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import AuditedViewSetMixin, record
from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdmin, is_admin
from apps.core.roles import effective_role

from .defaults import seed_widgets
from .models import DashboardWidget
from .serializers import DashboardWidgetSerializer, WidgetReorderSerializer
from .signals import broadcast_layout_change
from .sources import DataContext, allowed_roles, catalog, resolve, source_meta

logger = logging.getLogger(__name__)


@extend_schema(responses={200: dict})
@api_view(["GET"])
def dashboard(request):
    """The current user's dashboard: role-filtered widgets with their data, in display order."""
    role = effective_role(request.user)
    ctx = DataContext(request.user)
    out = []
    for w in DashboardWidget.objects.filter(is_active=True).order_by("position", "id"):
        if role not in (w.visible_roles or []) or source_meta(w.data_source) is None:
            continue
        # Defence in depth: never serve org-wide data to a role the source doesn't allow,
        # even if a stale or hand-edited widget row says otherwise.
        if role not in allowed_roles(w.data_source):
            continue
        try:
            data = resolve(w.data_source, ctx)
        except Exception:  # noqa: BLE001 - one broken widget must not take down the dashboard
            logger.exception("Dashboard widget %s failed", w.pk)
            data = None
        out.append({**DashboardWidgetSerializer(w).data, "data": data, "error": data is None})
    return Response({"widgets": out, "can_edit": is_admin(request.user)})


class DashboardWidgetViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    """Admin-only widget management. Everyone else gets the read-only /api/dashboard/."""

    queryset = DashboardWidget.objects.order_by("position", "id")
    serializer_class = DashboardWidgetSerializer
    permission_classes = [IsAdmin]
    pagination_class = None

    def perform_create(self, serializer):
        if "position" not in serializer.validated_data:
            last = DashboardWidget.objects.order_by("-position").values_list("position", flat=True).first()
            serializer.validated_data["position"] = (last or 0) + 1
        return super().perform_create(serializer)

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def sources(self, request):
        return Response({"sources": catalog(), "sizes": DashboardWidget.Size.choices, "types": DashboardWidget.Type.choices})

    @extend_schema(request=WidgetReorderSerializer, responses={200: dict})
    @action(detail=False, methods=["post"])
    def reorder(self, request):
        s = WidgetReorderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        ids = s.validated_data["ids"]
        with transaction.atomic():
            widgets = {w.pk: w for w in DashboardWidget.objects.select_for_update()}
            if len(ids) != len(set(ids)) or set(ids) != set(widgets):
                raise DomainError("Provide every widget id exactly once, in the new order.", field="ids")
            for pos, pk in enumerate(ids):
                widgets[pk].position = pos
            DashboardWidget.objects.bulk_update(widgets.values(), ["position"])
        record(
            AuditLog.Action.BULK_UPDATE,
            request.user,
            model="dashboard.dashboardwidget",
            object_repr="Reordered dashboard widgets",
            changes={"ids": ids},
        )
        broadcast_layout_change()
        return Response({"updated": len(ids)})

    @extend_schema(request=None, responses={200: dict})
    @action(detail=False, methods=["post"])
    def reset(self, request):
        created = seed_widgets(DashboardWidget, replace=True)
        record(
            AuditLog.Action.BULK_UPDATE,
            request.user,
            model="dashboard.dashboardwidget",
            object_repr="Dashboard reset to defaults",
        )
        broadcast_layout_change()
        return Response({"created": created})
