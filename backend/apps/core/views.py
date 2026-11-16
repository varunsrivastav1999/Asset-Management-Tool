import logging

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound
from rest_framework.parsers import MultiPartParser
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
        data = backups.status()
        restore = data["restore"]
        if restore and restore["state"] == "done":
            migrate_after_restore(restore.get("id"))
        return Response(data)

    @extend_schema(request=None, responses={202: dict})
    def post(self, request):
        try:
            backups.request_backup()
        except backups.BackupStorageError as exc:
            return Response({"detail": str(exc), "code": "backup_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        record(AuditLog.Action.CREATE, request.user, model="core.backup", object_repr="Manual database backup requested")
        return Response(backups.status(), status=status.HTTP_202_ACCEPTED)


class BackupUploadView(APIView):
    """Admin: upload a backup file (e.g. one downloaded earlier or from another server) so it can be restored."""

    permission_classes = [IsAdmin]
    parser_classes = [MultiPartParser]

    @extend_schema(request={"multipart/form-data": OpenApiTypes.OBJECT}, responses={201: dict})
    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": "Attach a .dump file.", "code": "invalid"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            saved = backups.save_upload(upload)
        except backups.BackupStorageError as exc:
            return Response({"detail": str(exc), "code": "backup_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        record(
            AuditLog.Action.CREATE,
            request.user,
            model="core.backup",
            object_repr=f"Uploaded backup {saved.name} ({upload.name}, {saved.size} bytes)",
        )
        return Response(saved.as_dict(), status=status.HTTP_201_CREATED)


def migrate_after_restore(restore_id) -> None:
    """A restored backup may come from an older version of the app: bring its schema up to date, once per restore."""
    if not restore_id or not cache.add(f"backup-restore-migrated:{restore_id}", True, timeout=60 * 60 * 24 * 30):
        return
    try:
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            logger.info("migrating restored database", extra={"restore": restore_id})
            call_command("migrate", interactive=False, verbosity=0)
    except Exception:
        cache.delete(f"backup-restore-migrated:{restore_id}")  # try again on the next status check
        logger.exception("migration after restore failed")


class BackupRestoreView(APIView):
    """Admin: replace the database with a backup. The backup service saves the current data first."""

    permission_classes = [IsAdmin]

    @extend_schema(request={"application/json": OpenApiTypes.OBJECT}, responses={202: dict})
    def post(self, request, name):
        if request.data.get("confirm") != name:
            return Response(
                {"detail": "Type the backup's name to confirm the restore.", "code": "confirm_required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not backups.service_online():
            return Response(
                {
                    "detail": "The backup service isn't running. Start it with: docker compose up -d backup",
                    "code": "backup_unavailable",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            backups.request_restore(name)
        except FileNotFoundError:
            raise NotFound("Backup not found.") from None
        except backups.RestoreBusy as exc:
            return Response({"detail": str(exc), "code": "restore_in_progress"}, status=status.HTTP_409_CONFLICT)
        except backups.BackupStorageError as exc:
            return Response({"detail": str(exc), "code": "backup_unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        record(AuditLog.Action.UPDATE, request.user, model="core.backup", object_repr=f"Restore of {name} requested")
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
