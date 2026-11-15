"""Dynamic host handling: serve the app on whatever address the machine has, with no IPs in config.

`DJANGO_ALLOWED_HOSTS` lists the public names you own (e.g. assets.example.com). On top of that, when
`ALLOW_PRIVATE_NETWORK_HOSTS` is on (the default), any private-network address is accepted automatically:
localhost, RFC 1918 / link-local / unique-local IPs (192.168.x.x, 10.x.x.x, 172.16-31.x.x, fe80::, fd00::),
and LAN-only names (`*.local`, `*.lan`, `*.home.arpa`, `*.internal`, single-label names such as `office-pc`).
So `http://<this machine's LAN IP>:2025` works from every device on the network, whatever the IP is today.

Links that leave the app (QR codes, PDF receipts, reminder emails) use `frontend_url()`: an explicit
`FRONTEND_URL` if set, otherwise the address the current request came in on, otherwise the last LAN/public
address someone used (remembered for background jobs), otherwise http://localhost:2025.
"""

import contextvars
import ipaddress

from django.conf import settings
from django.core.cache import cache
from django.http.request import split_domain_port, validate_host

LAN_SUFFIXES = (".local", ".lan", ".home.arpa", ".internal", ".localhost")
FALLBACK_URL = "http://localhost:2025"
_ORIGIN_CACHE_KEY = "core:frontend-origin"

_current_origin: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_origin", default=None)
_remembered = {"origin": None}  # per-process copy, so the cache is only written when the address changes


def is_private_host(host: str) -> bool:
    """True for addresses that can only be reached from the local network."""
    host = (host or "").strip().lower().rstrip(".")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not host:
        return False
    if host == "localhost" or host.endswith(LAN_SUFFIXES):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # A single-label name (no dots) only resolves on the local network.
        return "." not in host and all(c.isalnum() or c == "-" for c in host)
    return ip.is_private or ip.is_loopback or ip.is_link_local


def host_allowed(host: str) -> bool:
    """Whether a Host / Origin hostname (no port) may be served."""
    if not host:
        return False
    if validate_host(host, settings.TRUSTED_HOSTS):
        return True
    return settings.ALLOW_PRIVATE_NETWORK_HOSTS and is_private_host(host)


def split_host(raw: str) -> str:
    domain, _port = split_domain_port(raw or "")
    return domain


def set_current_origin(origin: str | None):
    """Bind the current request's origin (scheme://host[:port]); returns a token for `reset_current_origin`."""
    if origin and not settings.FRONTEND_URL:
        host = split_host(origin.split("://", 1)[-1])
        is_loopback = host in ("localhost", "127.0.0.1", "::1")
        if not is_loopback and _remembered["origin"] != origin:
            _remembered["origin"] = origin
            cache.set(_ORIGIN_CACHE_KEY, origin, None)
    return _current_origin.set(origin)


def reset_current_origin(token) -> None:
    _current_origin.reset(token)


def frontend_url() -> str:
    """Base URL for links that leave the app, without a trailing slash."""
    if settings.FRONTEND_URL:
        return settings.FRONTEND_URL
    current = _current_origin.get()
    if current:
        return current
    return cache.get(_ORIGIN_CACHE_KEY) or FALLBACK_URL
