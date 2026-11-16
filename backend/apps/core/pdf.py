"""PDF documents rendered with ReportLab (pure Python, no system deps)."""

import io
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.hosts import frontend_url

ACCENT = colors.HexColor("#047857")
DARK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")

_styles = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_styles["Heading1"], fontSize=18, textColor=DARK, spaceAfter=2)
H2 = ParagraphStyle("h2", parent=_styles["Heading2"], fontSize=11, textColor=ACCENT, spaceBefore=10, spaceAfter=4)
BODY = ParagraphStyle("body", parent=_styles["BodyText"], fontSize=9, leading=12, textColor=DARK)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, textColor=MUTED)


def _esc(value) -> str:
    from xml.sax.saxutils import escape

    return escape(str(value if value not in (None, "") else "—"))


def qr_drawing(payload: str, size: float = 28 * mm) -> Drawing:
    widget = QrCodeWidget(payload)
    x1, y1, x2, y2 = widget.getBounds()
    w, h = x2 - x1, y2 - y1
    d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
    d.add(widget)
    return d


def _header_footer(title):
    def draw(canv, doc):
        canv.saveState()
        canv.setFillColor(ACCENT)
        canv.rect(0, A4[1] - 6 * mm, A4[0], 6 * mm, fill=1, stroke=0)
        canv.setFont("Helvetica-Bold", 9)
        canv.setFillColor(DARK)
        canv.drawString(18 * mm, A4[1] - 14 * mm, settings.ORG_NAME.upper())
        canv.setFont("Helvetica", 8)
        canv.setFillColor(MUTED)
        canv.drawRightString(A4[0] - 18 * mm, A4[1] - 14 * mm, title)
        canv.drawString(18 * mm, 10 * mm, f"Generated {timezone.localtime():%Y-%m-%d %H:%M %Z}")
        canv.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canv.restoreState()

    return draw


def _kv_table(rows, col_widths=(38 * mm, 136 * mm)):
    data = [[Paragraph(f"<b>{_esc(k)}</b>", SMALL), Paragraph(_esc(v), BODY)] for k, v in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def _grid(header, rows, widths):
    data = [[Paragraph(f"<b>{_esc(h)}</b>", SMALL) for h in header]]
    data += [[Paragraph(_esc(c), BODY) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def _signature_cell(field_file, label, name, when):
    parts = []
    if field_file:
        try:
            with field_file.open("rb") as fh:
                parts.append(Image(io.BytesIO(fh.read()), width=55 * mm, height=22 * mm, kind="proportional"))
        except (FileNotFoundError, OSError, ValueError):
            parts.append(Paragraph("<i>signature unavailable</i>", SMALL))
    else:
        parts.append(Spacer(1, 22 * mm))
    parts.append(Paragraph(f"<b>{_esc(label)}</b>", SMALL))
    parts.append(Paragraph(_esc(name), BODY))
    parts.append(Paragraph(_esc(f"{timezone.localtime(when):%Y-%m-%d %H:%M}" if when else "Not signed"), SMALL))
    return parts


def _build(story, title) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=18 * mm, title=title
    )
    draw = _header_footer(title)
    doc.build(story, onFirstPage=draw, onLaterPages=draw)
    return buf.getvalue()


def _person(user, department=None):
    if user:
        bits = [user.get_full_name() or user.email, user.email]
        if user.employee_id:
            bits.append(f"ID {user.employee_id}")
        return " · ".join(bits)
    return department.name if department else "Store / Inventory"


def handover_pdf(handover) -> bytes:
    title = f"Handover receipt {handover.reference}"
    head = Table(
        [
            [
                [
                    Paragraph(f"Asset {handover.get_type_display()} Receipt", H1),
                    Paragraph(
                        f"Reference <b>{_esc(handover.reference)}</b> · Status <b>{_esc(handover.get_status_display())}</b>", BODY
                    ),
                ],
                qr_drawing(f"{frontend_url()}/handovers/{handover.pk}"),
            ]
        ],
        colWidths=[144 * mm, 30 * mm],
    )
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story = [head, Paragraph("Parties", H2)]
    story.append(
        _kv_table(
            [
                ("From", _person(handover.from_user, handover.from_department)),
                ("To", _person(handover.to_user, handover.to_department)),
                ("Department", (handover.to_department or handover.from_department or "—")),
                ("Location", handover.to_location or "—"),
                ("Created by", handover.created_by.get_full_name() if handover.created_by else "—"),
                ("Created", f"{timezone.localtime(handover.created_at):%Y-%m-%d %H:%M}"),
                ("Expected return", handover.expected_return_date or "—"),
            ]
        )
    )
    story.append(Paragraph("Assets", H2))
    items = list(handover.items.select_related("asset", "asset__category"))
    story.append(
        _grid(
            ["Tag", "Asset", "Category", "Serial", "Condition"],
            [
                [i.asset.asset_tag, i.asset.name, i.asset.category.name, i.asset.serial_number or "—", i.get_condition_display()]
                for i in items
            ],
            [26 * mm, 58 * mm, 32 * mm, 34 * mm, 24 * mm],
        )
    )
    if handover.notes:
        story += [Paragraph("Notes", H2), Paragraph(_esc(handover.notes), BODY)]
    story.append(Paragraph("Acknowledgement", H2))
    story.append(
        Paragraph(
            "By signing, the recipient confirms the assets listed above were handed over in the stated condition and "
            "accepts responsibility for their care in accordance with company policy.",
            SMALL,
        )
    )
    story.append(Spacer(1, 4 * mm))
    sig = Table(
        [
            [
                _signature_cell(
                    handover.issuer_signature,
                    "Issued / processed by",
                    handover.created_by.get_full_name() if handover.created_by else "",
                    handover.created_at if handover.issuer_signature else None,
                ),
                _signature_cell(handover.signature, "Signed by", handover.signed_name, handover.signed_at),
            ]
        ],
        colWidths=[87 * mm, 87 * mm],
    )
    sig.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LINEABOVE", (0, 0), (-1, 0), 0.4, LINE)]))
    story.append(sig)
    return _build(story, title)


def receipt_pdf(receipt) -> bytes:
    title = f"Goods received note {receipt.reference}"
    story = [Paragraph("Goods Received Note", H1), Paragraph(f"Reference <b>{_esc(receipt.reference)}</b>", BODY)]
    story.append(Paragraph("Details", H2))
    story.append(
        _kv_table(
            [
                ("Vendor", receipt.vendor or "—"),
                ("Received", receipt.received_date),
                ("Invoice #", receipt.invoice_number),
                ("PO #", receipt.po_number),
                ("Location", receipt.location or "—"),
                ("Received by", receipt.received_by.get_full_name() if receipt.received_by else "—"),
            ]
        )
    )
    assets = list(receipt.assets.select_related("category").order_by("asset_tag"))
    total = sum((a.purchase_cost or 0) for a in assets)
    story.append(Paragraph(f"Assets received ({len(assets)})", H2))
    story.append(
        _grid(
            ["Tag", "Asset", "Category", "Serial", "Cost"],
            [
                [a.asset_tag, a.name, a.category.name, a.serial_number or "—", f"{a.purchase_cost or 0:,.2f} {a.currency}"]
                for a in assets
            ],
            [26 * mm, 58 * mm, 32 * mm, 34 * mm, 24 * mm],
        )
    )
    story.append(Paragraph(f"<b>Total value:</b> {total:,.2f}", BODY))
    if receipt.notes:
        story += [Paragraph("Notes", H2), Paragraph(_esc(receipt.notes), BODY)]
    story.append(Spacer(1, 6 * mm))
    story += _signature_cell(receipt.signature, "Received & verified by", receipt.signed_name, receipt.signed_at)
    return _build(story, title)


@dataclass(frozen=True)
class Label:
    """One sticker: QR code plus the code in large type, a title and an optional detail line."""

    code: str
    title: str
    qr_payload: str
    detail: str = ""


def labels_pdf(labels: list[Label]) -> bytes:
    """A4 sheet of 3 x 8 labels (assets, table rows, …) with QR code, code, title and organisation."""
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Labels")
    cols, rows = 3, 8
    margin_x, margin_y = 8 * mm, 12 * mm
    w = (A4[0] - 2 * margin_x) / cols
    h = (A4[1] - 2 * margin_y) / rows
    for idx, label in enumerate(labels):
        pos = idx % (cols * rows)
        if idx and pos == 0:
            c.showPage()
        col, row = pos % cols, pos // cols
        x = margin_x + col * w
        y = A4[1] - margin_y - (row + 1) * h
        c.setStrokeColor(LINE)
        c.roundRect(x + 2, y + 2, w - 4, h - 4, 4, stroke=1, fill=0)
        qr = qr_drawing(label.qr_payload, size=h - 8 * mm)
        qr.drawOn(c, x + 3 * mm, y + 4 * mm)
        tx = x + h - 2 * mm
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(tx, y + h - 10 * mm, label.code[:24])
        c.setFont("Helvetica", 7)
        c.drawString(tx, y + h - 14 * mm, (label.title or "")[:28])
        c.setFillColor(MUTED)
        if label.detail:
            c.drawString(tx, y + h - 18 * mm, label.detail[:30])
        c.drawString(tx, y + 5 * mm, settings.ORG_NAME[:28])
    c.save()
    return buf.getvalue()


def table_pdf(title: str, header: list[str], rows: list[list]) -> bytes:
    """Landscape table export (used for reminder attachments)."""
    from reportlab.lib.pagesizes import landscape

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=20 * mm, bottomMargin=16 * mm, title=title
    )
    width = landscape(A4)[0] - 24 * mm
    col_w = [width / max(1, len(header))] * len(header)
    story = [
        Paragraph(_esc(title), H1),
        Spacer(1, 3 * mm),
        _grid(header, [[str(c) for c in r] for r in rows] or [["—"] * len(header)], col_w),
    ]
    draw = _header_footer(title)
    doc.build(story, onFirstPage=draw, onLaterPages=draw)
    return buf.getvalue()
