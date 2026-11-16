import os
import tempfile

from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False
SECRET_KEY = "test-secret-key-not-for-production-use-0123456789"
SIMPLE_JWT["SIGNING_KEY"] = SECRET_KEY  # noqa: F405
TRUSTED_HOSTS = ["*"]
DATABASES = {"default": env.db("DATABASE_URL", default="postgres://localhost/asset_test")}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
_tmp = tempfile.mkdtemp(prefix="ams-test-")
MEDIA_ROOT = f"{_tmp}/media"
PRIVATE_MEDIA_ROOT = f"{_tmp}/private"
STATIC_ROOT = f"{_tmp}/static"
os.makedirs(STATIC_ROOT, exist_ok=True)
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405
JWT_REFRESH_COOKIE["secure"] = False  # noqa: F405
LOGGING["root"]["level"] = "WARNING"  # noqa: F405
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SMTP_HOST = "smtp.test"
EMAIL_HOST = "smtp.test"

# Tests create and flush their own database; no connection pool there.
DATABASES["default"].get("OPTIONS", {}).pop("pool", None)  # noqa: F405
DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405
