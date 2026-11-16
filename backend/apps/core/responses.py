from django.http import HttpResponse


def file_response(content: bytes, content_type: str, filename: str, inline: bool = False) -> HttpResponse:
    """Generated file (PDF, QR, barcode, export) as a download or inline, never cached."""
    response = HttpResponse(content, content_type=content_type)
    disposition = "inline" if inline else "attachment"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    response["Cache-Control"] = "private, max-age=0, no-store"
    return response
