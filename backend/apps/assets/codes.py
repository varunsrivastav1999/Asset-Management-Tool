"""QR code and Code128 barcode rendering."""

import io

import barcode
import qrcode
import qrcode.image.svg
from barcode.writer import ImageWriter, SVGWriter


def qr_png(payload: str, box_size: int = 10) -> bytes:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def qr_svg(payload: str) -> bytes:
    img = qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    out = io.BytesIO()
    img.save(out)
    return out.getvalue()


def barcode_svg(value: str) -> bytes:
    code = barcode.get("code128", value, writer=SVGWriter())
    out = io.BytesIO()
    code.write(out, options={"module_height": 12.0, "font_size": 8, "text_distance": 4, "quiet_zone": 2})
    return out.getvalue()


def barcode_png(value: str) -> bytes:
    code = barcode.get("code128", value, writer=ImageWriter())
    out = io.BytesIO()
    code.write(out, options={"module_height": 12.0, "font_size": 8, "text_distance": 4, "quiet_zone": 2})
    return out.getvalue()
