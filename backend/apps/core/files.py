import base64
import binascii
import io
import os
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers


@deconstructible
class PrivateStorage(FileSystemStorage):
    """Storage for sensitive files (signatures). Never mapped to a public URL."""

    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):  # pragma: no cover - deliberately unsupported
        raise NotImplementedError("Private files are only streamed through authenticated API views.")


private_storage = PrivateStorage()


def upload_to(prefix: str):
    def _path(instance, filename):
        ext = (filename.rsplit(".", 1)[-1] if "." in filename else "bin").lower()[:5]
        return f"{prefix}/{uuid.uuid4().hex}.{ext}"

    _path.__name__ = f"upload_to_{prefix.replace('/', '_')}"
    return _path


# Named callables are required for migrations to serialize upload_to.
def asset_photo_path(instance, filename):
    return upload_to("assets/photos")(instance, filename)


def avatar_path(instance, filename):
    return upload_to("avatars")(instance, filename)


def invoice_path(instance, filename):
    return upload_to("invoices")(instance, filename)


def signature_path(instance, filename):
    return upload_to("signatures")(instance, filename)


MAX_SIGNATURE_BYTES = 512 * 1024


def decode_signature(data_url: str) -> ContentFile:
    """Turn a canvas `data:image/png;base64,...` string into a validated PNG file."""
    if not data_url or not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        raise serializers.ValidationError("Signature must be a data:image/... URL.")
    try:
        header, b64 = data_url.split(",", 1)
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise serializers.ValidationError("Signature is not valid base64.") from exc
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise serializers.ValidationError("Signature image is too large.")
    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise serializers.ValidationError("Signature is not a valid image.") from exc
    if img.width < 50 or img.height < 20:
        raise serializers.ValidationError("Signature image is too small.")
    # Reject blank canvases: require some non-transparent ink.
    alpha = img.getchannel("A")
    if alpha.getbbox() is None:
        raise serializers.ValidationError("Signature is empty.")
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return ContentFile(out.getvalue(), name=f"{uuid.uuid4().hex}.png")


def validate_image_upload(file):
    max_bytes = settings.MAX_IMAGE_UPLOAD_MB * 1024 * 1024
    if file.size > max_bytes:
        raise serializers.ValidationError(f"Image exceeds {settings.MAX_IMAGE_UPLOAD_MB} MB.")
    try:
        img = Image.open(file)
        img.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise serializers.ValidationError("Upload a valid image file.") from exc
    finally:
        file.seek(0)
    if (img.format or "").upper() not in {"JPEG", "PNG", "WEBP", "GIF"}:
        raise serializers.ValidationError("Supported formats: JPEG, PNG, WEBP, GIF.")
    return file


ALLOWED_DOCUMENT_TYPES = {"pdf", "png", "jpg", "jpeg", "webp"}


def validate_document_upload(file, max_mb: int = 10):
    """Bills/invoices: PDF or image, size-limited, content sniffed (not just the extension)."""
    ext = (file.name.rsplit(".", 1)[-1] if "." in file.name else "").lower()
    if ext not in ALLOWED_DOCUMENT_TYPES:
        raise serializers.ValidationError("Upload a PDF or image (PNG, JPG, WEBP).")
    if file.size > max_mb * 1024 * 1024:
        raise serializers.ValidationError(f"File exceeds {max_mb} MB.")
    head = file.read(8)
    file.seek(0)
    if ext == "pdf":
        if not head.startswith(b"%PDF"):
            raise serializers.ValidationError("That file isn't a valid PDF.")
    else:
        validate_image_upload(file)
    return file
