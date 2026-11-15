"""Tiny, safe {{variable}} templating (no logic, no attribute access, unknown names render empty)."""

import html
import re

VAR_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")

VARIABLES = {
    "asset_name": "Asset name",
    "asset_tag": "Asset tag",
    "due_date": "Due / expiry date",
    "days_left": "Days until the date (negative = overdue)",
    "user_name": "Asset holder's name",
    "recipient_name": "Recipient's name",
    "department": "Department",
    "section_name": "Section (table) name",
    "reference": "Handover / receipt reference",
    "status": "Status",
    "category": "Category",
    "count": "Number of matching rows",
    "item_name": "Row name (any section)",
    "link": "Link to the item",
    "org_name": "Organisation name",
}

SAMPLE_CONTEXT = {
    "asset_name": "Dell Latitude 7440",
    "asset_tag": "AST-000042",
    "due_date": "15 Dec 2026",
    "days_left": "7",
    "user_name": "Eve Employee",
    "recipient_name": "Max Manager",
    "department": "Engineering",
    "section_name": "Assets",
    "reference": "HND-000123",
    "status": "Assigned",
    "category": "Laptops",
    "count": "3",
    "item_name": "Dell Latitude 7440",
    "link": "https://assets.example.com/assets/42",
    "org_name": "Asset Management Tools",
}


def render(text: str, context: dict) -> str:
    return VAR_RE.sub(lambda m: str(context.get(m.group(1), "")), text or "")


def render_subject(text: str, context: dict) -> str:
    # Header-injection safe: subjects are single-line.
    return " ".join(render(text, context).split())[:200]


def render_html(text: str, context: dict) -> str:
    safe = {k: html.escape(str(v)) for k, v in context.items()}
    body = render(html.escape(text or ""), safe)
    paragraphs = "".join(f'<p style="margin:0 0 12px">{p.replace(chr(10), "<br>")}</p>' for p in body.split("\n\n"))
    return (
        '<div style="font-family:Inter,Arial,sans-serif;font-size:14px;line-height:1.55;color:#0b1220;max-width:560px">'
        f"{paragraphs}"
        '<p style="margin-top:24px;font-size:12px;color:#5b6478">Sent by '
        f"{html.escape(str(context.get('org_name', '')))} · manage your notification preferences in your profile.</p></div>"
    )


def sms_text(template_text: str, context: dict, link: str = "", limit: int = 160) -> str:
    """Render the SMS text, keeping a link intact and truncating the message to fit `limit` characters."""
    text = " ".join(render(template_text, context).split())
    if not link:
        return text[:limit]
    room = limit - len(link) - 1
    if room < 10:
        return link[:limit]
    if len(text) > room:
        text = text[: room - 1].rstrip() + "…"
    return f"{text} {link}"
