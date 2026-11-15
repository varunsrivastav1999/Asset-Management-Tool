import logging

from django.core.cache import cache
from django.db import connection
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.audit.services import record

from . import backups
from .permissions import IsAdmin

logger = logging.getLogger(__name__)


@extend_schema(exclude=True)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def liveness(request):
    """Process is up. Used by container health checks."""
    return Response({"status": "ok"})


@extend_schema(exclude=True)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def readiness(request):
    """Dependencies reachable: database and cache/redis."""
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001
        logger.exception("Readiness: database check failed")
        checks["database"] = "error"
    try:
        cache.set("health:ping", "1", 5)
        checks["cache"] = "ok" if cache.get("health:ping") == "1" else "degraded"
    except Exception:  # noqa: BLE001
        checks["cache"] = "error"
    healthy = checks["database"] == "ok"
    return Response({"status": "ok" if healthy else "error", "checks": checks}, status=200 if healthy else 503)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def app_config(request):
    """Public, non-secret display settings the SPA needs before sign-in (currency and number formatting)."""
    from django.conf import settings

    return Response(
        {"org_name": settings.ORG_NAME, "currency": settings.DEFAULT_CURRENCY, "currency_locale": settings.CURRENCY_LOCALE}
    )


class BackupsView(APIView):
    """Admin: list database backups and request a new one."""

    permission_classes = [IsAdmin]

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response(backups.status())

    @extend_schema(request=None, responses={202: dict})
    def post(self, request):
        try:
            backups.request_backup()
        except backups.BackupStorageError as exc:
            return Response({"detail": str(exc), "code": "backup_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        record(AuditLog.Action.CREATE, request.user, model="core.backup", object_repr="Manual database backup requested")
        return Response(backups.status(), status=status.HTTP_202_ACCEPTED)


class BackupFileView(APIView):
    """Admin: download or delete one backup file."""

    permission_classes = [IsAdmin]

    def _path(self, name):
        path = backups.resolve(name)
        if path is None:
            raise NotFound("Backup not found.")
        return path

    @extend_schema(operation_id="backups_download", responses={200: OpenApiTypes.BINARY})
    def get(self, request, name):
        path = self._path(name)
        record(AuditLog.Action.EXPORT, request.user, model="core.backup", object_repr=f"Downloaded {name}")
        return FileResponse(path.open("rb"), as_attachment=True, filename=name, content_type="application/octet-stream")

    @extend_schema(operation_id="backups_delete", responses={204: None})
    def delete(self, request, name):
        self._path(name).unlink()
        record(AuditLog.Action.DELETE, request.user, model="core.backup", object_repr=f"Deleted {name}")
        return Response(status=status.HTTP_204_NO_CONTENT)
