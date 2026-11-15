import django_filters
from rest_framework import serializers, viewsets

from apps.core.permissions import IsAdmin

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "actor_name",
            "actor_email",
            "action",
            "model",
            "object_id",
            "object_repr",
            "changes",
            "ip_address",
            "user_agent",
            "request_id",
            "created_at",
        ]

    def get_actor_name(self, obj) -> str | None:
        return obj.actor.get_full_name() if obj.actor else "System"


class AuditLogFilter(django_filters.FilterSet):
    date_from = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields = ["action", "model", "object_id", "actor"]


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor")
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    filterset_class = AuditLogFilter
    search_fields = ["object_repr", "actor__email", "model", "request_id", "ip_address"]
    ordering_fields = ["created_at", "action", "model"]
