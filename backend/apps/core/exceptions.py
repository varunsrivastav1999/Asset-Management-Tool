import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """Raised by service-layer code when a business rule is violated."""

    def __init__(self, message, code="invalid", field=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.field = field


def api_exception_handler(exc, context):
    if isinstance(exc, DomainError):
        key = exc.field or "detail"
        payload = {key: [exc.message] if exc.field else exc.message, "code": exc.code}
        return Response(payload, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    if isinstance(exc, ProtectedError):
        return Response(
            {"detail": "This record is referenced by other records and cannot be deleted.", "code": "protected"},
            status=status.HTTP_409_CONFLICT,
        )
    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", exc_info=exc)
    return response
