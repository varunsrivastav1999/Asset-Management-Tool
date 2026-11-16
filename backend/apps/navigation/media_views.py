"""Uploads for Media columns: photos and documents attached to table cells.

Files live in private storage. Upload needs a manager or admin (the same people who edit cell values); download
needs to be able to see the page the file belongs to. Content is sniffed, never trusted from the extension.
"""

from django.conf import settings
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.exceptions import DomainError
from apps.core.files import validate_image_upload
from apps.core.permissions import IsManager, is_admin
from apps.core.roles import effective_role

from .models import SidebarItem, TableColumn, TableMedia

# extension -> (content type, check on the first bytes)
_ZIP = b"PK\x03\x04"
ALLOWED = {
    "jpg": ("image/jpeg", None),
    "jpeg": ("image/jpeg", None),
    "png": ("image/png", None),
    "webp": ("image/webp", None),
    "gif": ("image/gif", None),
    "pdf": ("application/pdf", lambda h: h.startswith(b"%PDF")),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", lambda h: h.startswith(_ZIP)),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", lambda h: h.startswith(_ZIP)),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", lambda h: h.startswith(_ZIP)),
    "csv": ("text/csv", lambda h: b"\x00" not in h),
    "txt": ("text/plain", lambda h: b"\x00" not in h),
    "mp4": ("video/mp4", lambda h: h[4:8] == b"ftyp"),
}


def can_view(user, item: SidebarItem) -> bool:
    return is_admin(user) or (item.is_active and effective_role(user) in (item.visible_roles or []))


def validate_media_file(upload) -> str:
    """Returns the content type to store, or raises ValidationError."""
    ext = (upload.name.rsplit(".", 1)[-1] if "." in upload.name else "").lower()
    if ext not in ALLOWED:
        raise serializers.ValidationError({"file": "Upload a photo (JPG, PNG, WEBP, GIF), PDF, Office file, CSV/TXT or MP4."})
    limit = settings.MAX_MEDIA_UPLOAD_MB
    if upload.size > limit * 1024 * 1024:
        raise serializers.ValidationError({"file": f"File exceeds {limit} MB."})
    content_type, check = ALLOWED[ext]
    if check is None:
        validate_image_upload(upload)  # decodes the image; rejects disguised files
    else:
        head = upload.read(4096)
        upload.seek(0)
        if not check(head):
            raise serializers.ValidationError({"file": f"That file isn't a valid .{ext} file."})
    return content_type


class TableMediaUploadView(APIView):
    """POST multipart {file, table_item, column} -> the cell value to save."""

    permission_classes = [IsManager]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(request={"multipart/form-data": OpenApiTypes.OBJECT}, responses={201: dict})
    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise DomainError("Attach a file.", field="file")
        item = (
            SidebarItem.objects.filter(pk=str(request.data.get("table_item", ""))).first()
            if str(request.data.get("table_item", "")).isdigit()
            else None
        )
        if item is None or not can_view(request.user, item):
            raise NotFound("Unknown table.")
        column = TableColumn.objects.filter(
            sidebar_item=item, key=request.data.get("column", ""), is_builtin=False, column_type=TableColumn.Type.MEDIA
        ).first()
        if column is None:
            raise DomainError("That column doesn't take uploads.", field="column")
        content_type = validate_media_file(upload)
        media = TableMedia.objects.create(
            sidebar_item=item,
            column_key=column.key,
            file=upload,
            name=upload.name[:255],
            content_type=content_type,
            size=upload.size,
            uploaded_by=request.user,
        )
        record(
            AuditLog.Action.CREATE,
            request.user,
            model="navigation.tablemedia",
            object_id=str(media.pk),
            object_repr=f"{media.name} → {item.name} / {column.name}",
        )
        return Response(media.as_value(), status=status.HTTP_201_CREATED)


class TableMediaFileView(APIView):
    """GET the file (inline for photos, as a download otherwise)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="table_media_file", responses={200: OpenApiTypes.BINARY})
    def get(self, request, pk):
        media = TableMedia.objects.select_related("sidebar_item").filter(pk=pk).first()
        if media is None or not can_view(request.user, media.sidebar_item):
            raise NotFound("File not found.")
        try:
            handle = media.file.open("rb")
        except FileNotFoundError as exc:
            raise NotFound("File not found.") from exc
        response = FileResponse(handle, as_attachment=not media.is_image, filename=media.name, content_type=media.content_type)
        response["Cache-Control"] = "private, max-age=3600"
        response["Content-Security-Policy"] = "sandbox"  # never run anything a file might contain
        return response
