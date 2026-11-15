"""Shared bill/invoice upload/download action for models with an `invoice_file` (private storage)."""

from django.http import FileResponse
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.exceptions import DomainError
from apps.core.files import validate_document_upload
from apps.core.permissions import is_manager


class InvoiceFileMixin:
    @action(detail=True, methods=["get", "post", "delete"], url_path="invoice", parser_classes=[MultiPartParser, FormParser])
    def invoice(self, request, pk=None):
        obj = self.get_object()  # read access already scoped by get_queryset
        if request.method == "GET":
            if not obj.invoice_file:
                raise NotFound("No bill uploaded.")
            resp = FileResponse(
                obj.invoice_file.open("rb"), as_attachment=True, filename=obj.invoice_file.name.rsplit("/", 1)[-1]
            )
            resp["Cache-Control"] = "private, no-store"
            return resp
        if not is_manager(request.user):
            self.permission_denied(request, message="Manager or administrator role required.")
        if request.method == "DELETE":
            if obj.invoice_file:
                obj.invoice_file.delete(save=False)
            obj.invoice_file = None
            obj.save(update_fields=["invoice_file"])
            record(AuditLog.Action.UPDATE, request.user, obj, {"invoice_file": "removed"})
            return Response(status=204)
        upload = request.FILES.get("file")
        if upload is None:
            raise DomainError("Attach a PDF or image.", field="file")
        validate_document_upload(upload)
        if obj.invoice_file:
            obj.invoice_file.delete(save=False)
        obj.invoice_file.save(upload.name, upload, save=False)
        obj.save(update_fields=["invoice_file"])
        record(AuditLog.Action.UPDATE, request.user, obj, {"invoice_file": obj.invoice_file.name})
        return Response({"has_invoice": True, "name": obj.invoice_file.name.rsplit("/", 1)[-1]})
