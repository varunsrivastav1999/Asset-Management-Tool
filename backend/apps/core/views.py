import logging

from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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
