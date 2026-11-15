import contextvars
import logging
import time
import uuid

logger = logging.getLogger("apps.request")

_request_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar("request_ctx", default=None)


def get_request_context() -> dict:
    return _request_ctx.get() or {}


def client_ip(request) -> str | None:
    # nginx sets X-Real-IP to the actual peer; never trust the left-most X-Forwarded-For blindly.
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR")


class RequestContextMiddleware:
    """Attaches a request id and client metadata to a context var for logs and audit entries."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get("HTTP_X_REQUEST_ID", "")
        request_id = incoming[:64] if incoming else uuid.uuid4().hex
        request.request_id = request_id
        token = _request_ctx.set(
            {
                "request_id": request_id,
                "ip": client_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", "")[:255],
            }
        )
        start = time.monotonic()
        try:
            response = self.get_response(request)
        finally:
            _request_ctx.reset(token)
        response["X-Request-ID"] = request_id
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        if not request.path.startswith("/api/health"):
            logger.info(
                "%s %s %s %sms",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
                extra={"request_id": request_id, "status": response.status_code, "duration_ms": duration_ms},
            )
        return response


class HostValidationMiddleware:
    """Validates the Host header against `TRUSTED_HOSTS` plus any private-network address (see core.hosts).

    Django's own ALLOWED_HOSTS check can't express "any LAN address", so it is set to ["*"] and this middleware,
    which runs first, does the real check. It also binds the request's origin so links in QR codes, PDFs and
    emails point at the address the user actually used.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.core.exceptions import DisallowedHost

        from .hosts import host_allowed, reset_current_origin, set_current_origin, split_host

        raw = request._get_raw_host()
        if not host_allowed(split_host(raw)):
            raise DisallowedHost(f"Invalid HTTP_HOST header: {raw!r}. Add it to DJANGO_ALLOWED_HOSTS.")
        token = set_current_origin(f"{request.scheme}://{raw}")
        try:
            return self.get_response(request)
        finally:
            reset_current_origin(token)
