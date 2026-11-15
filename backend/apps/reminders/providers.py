"""Delivery providers. Secrets are read from environment-backed settings only."""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import uuid
from email.utils import make_msgid

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    """Temporary or permanent delivery failure (the task decides whether to retry)."""


def send_email(to: str, subject: str, text: str, html: str, attachments: list[tuple[str, bytes, str]], sender_name: str) -> str:
    msg_id = make_msgid(domain=getattr(settings, "EMAIL_MESSAGE_ID_DOMAIN", "assets.local"))
    from_email = f"{sender_name} <{settings.DEFAULT_FROM_EMAIL}>" if sender_name else settings.DEFAULT_FROM_EMAIL
    message = EmailMultiAlternatives(
        subject=subject, body=text, from_email=from_email, to=[to], headers={"Message-ID": msg_id}, connection=get_connection()
    )
    if html:
        message.attach_alternative(html, "text/html")
    for name, content, mimetype in attachments:
        message.attach(name, content, mimetype)
    try:
        message.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 - SMTP errors vary; surface as DeliveryError for retry
        raise DeliveryError(f"SMTP error: {exc}") from exc
    return msg_id


class ConsoleSMS:
    """Development provider: logs the message instead of sending it."""

    def send(self, to: str, text: str, sender: str) -> str:
        message_id = f"console-{uuid.uuid4().hex[:12]}"
        logger.info("SMS (console) to %s from %s: %s", to, sender or "-", text)
        return message_id


def _post(url: str, data: dict, headers: dict, form=True) -> dict:
    body = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")  # noqa: S310 - fixed https provider URLs
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise DeliveryError(f"HTTP {exc.code}: {exc.read()[:300].decode(errors='replace')}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DeliveryError(f"Network error: {exc}") from exc


class TwilioSMS:
    """SMS_API_KEY = "<ACCOUNT_SID>:<AUTH_TOKEN>"."""

    def send(self, to: str, text: str, sender: str) -> str:
        sid, _, token = (settings.SMS_API_KEY or "").partition(":")
        if not (sid and token and sender):
            raise DeliveryError("Twilio needs SMS_API_KEY=SID:TOKEN and a sender ID / number.")
        auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
        data = _post(
            f"https://api.twilio.com/2010-04-01/Accounts/{urllib.parse.quote(sid)}/Messages.json",
            {"To": to, "From": sender, "Body": text},
            {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
        )
        return str(data.get("sid", ""))


class Msg91SMS:
    """SMS_API_KEY = MSG91 auth key."""

    def send(self, to: str, text: str, sender: str) -> str:
        if not settings.SMS_API_KEY:
            raise DeliveryError("MSG91 needs SMS_API_KEY.")
        data = _post(
            "https://api.msg91.com/api/v2/sendsms",
            {"sender": sender, "route": "4", "sms": [{"message": text, "to": [to.lstrip("+")]}]},
            {"authkey": settings.SMS_API_KEY, "Content-Type": "application/json"},
            form=False,
        )
        if data.get("type") == "error":
            raise DeliveryError(f"MSG91: {data.get('message')}")
        return str(data.get("message", ""))


PROVIDERS = {"console": ConsoleSMS, "twilio": TwilioSMS, "msg91": Msg91SMS}


def get_sms_provider(name: str):
    return PROVIDERS.get(name, ConsoleSMS)()


def smtp_configured() -> bool:
    return bool(getattr(settings, "EMAIL_HOST", "")) and settings.EMAIL_BACKEND.endswith("smtp.EmailBackend")


def sms_configured(provider: str) -> bool:
    return provider == "console" or bool(settings.SMS_API_KEY)
