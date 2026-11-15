from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env

DEBUG = False

if SECRET_KEY.startswith(("insecure", "change-me")) or len(SECRET_KEY) < 40:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a strong value (>= 40 chars) in production.")

# TLS is terminated at nginx, which forwards X-Forwarded-Proto. The same HTTPS switch nginx uses
# (auto = on) decides the secure defaults below; each can still be overridden on its own.
HTTPS_ENABLED = env("HTTPS", default="auto").strip().lower() not in ("off", "false", "0", "no")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=HTTPS_ENABLED)
SECURE_REDIRECT_EXEMPT = [r"^api/health/"]
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = env.bool("DJANGO_HSTS_PRELOAD", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = env.bool("DJANGO_SECURE_COOKIES", default=HTTPS_ENABLED)
CSRF_COOKIE_SECURE = env.bool("DJANGO_SECURE_COOKIES", default=HTTPS_ENABLED)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
JWT_REFRESH_COOKIE["secure"] = env.bool("JWT_COOKIE_SECURE", default=HTTPS_ENABLED)  # noqa: F405

# HSTS preload is a hard-to-undo, opt-in decision; don't fail `check --deploy` while it's off.
SILENCED_SYSTEM_CHECKS = [] if SECURE_HSTS_PRELOAD else ["security.W021"]
