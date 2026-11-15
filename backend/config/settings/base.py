"""Base settings shared by every environment. All secrets/config come from env vars."""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    environ.Env.read_env(str(_env_file), overwrite=False)


def _secret_key() -> str:
    """DJANGO_SECRET_KEY, else the key the container entrypoint generated and persisted, else a dev placeholder."""
    value = env("DJANGO_SECRET_KEY", default="")
    if value:
        return value
    key_file = Path(env("PRIVATE_MEDIA_ROOT", default=str(BASE_DIR / "private_media"))) / ".django_secret_key"
    try:
        return key_file.read_text().strip() or "insecure-dev-only-key-change-me"
    except OSError:
        return "insecure-dev-only-key-change-me"


SECRET_KEY = _secret_key()
DEBUG = env.bool("DJANGO_DEBUG", default=False)
# Public names you own; private-network addresses (LAN IPs, *.local …) are accepted automatically when
# ALLOW_PRIVATE_NETWORK_HOSTS is on, so the app works on any device at http://<machine IP>:2025 without
# listing IPs. HostValidationMiddleware enforces this, so Django's own check is opened up.
TRUSTED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
ALLOW_PRIVATE_NETWORK_HOSTS = env.bool("ALLOW_PRIVATE_NETWORK_HOSTS", default=True)
ALLOWED_HOSTS = ["*"]

ORG_NAME = env("ORG_NAME", default="Asset Management Tools")
# Empty = use the address each request came in on (see apps.core.hosts.frontend_url).
FRONTEND_URL = env("FRONTEND_URL", default="").rstrip("/")
ADMIN_URL = env("DJANGO_ADMIN_URL", default="admin/")

INSTALLED_APPS = [
    "daphne",
    "config.admin_site.SuperuserAdminConfig",  # django.contrib.admin, superuser-only
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "channels",
    # local
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.assets",
    "apps.workflows",
    "apps.maintenance",
    "apps.notifications",
    "apps.dashboard",
    "apps.navigation",
    "apps.reminders",
]

MIDDLEWARE = [
    "apps.core.middleware.HostValidationMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "apps.core.middleware.RequestContextMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://asset:asset@localhost:5432/asset"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = env("STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))
MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))
# Signatures live outside MEDIA_ROOT so nginx never serves them publicly.
PRIVATE_MEDIA_ROOT = env("PRIVATE_MEDIA_ROOT", default=str(BASE_DIR / "private_media"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
MAX_IMAGE_UPLOAD_MB = env.int("MAX_IMAGE_UPLOAD_MB", default=10)
MAX_IMPORT_ROWS = env.int("MAX_IMPORT_ROWS", default=5000)

# --- Redis: broker (db0), cache (db1), channels (db2) -----------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("CACHE_URL", default=f"{REDIS_URL}/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,  # cache outage must not take the API down
        },
        "KEY_PREFIX": "ams",
        "TIMEOUT": 300,
    }
}
DJANGO_REDIS_LOG_IGNORED_EXCEPTIONS = True

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("CHANNELS_REDIS_URL", default=f"{REDIS_URL}/2")], "capacity": 1500, "expiry": 30},
    }
}

# --- DRF / JWT --------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "apps.core.filters.ColumnSearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="60/min"),
        "user": env("THROTTLE_USER", default="1200/min"),
        "login": env("THROTTLE_LOGIN", default="10/min"),
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
}
JWT_REFRESH_COOKIE = {
    "name": "ams_refresh",
    "path": "/api/auth/",
    "secure": env.bool("JWT_COOKIE_SECURE", default=not DEBUG),
    "samesite": "Strict",
    "httponly": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": f"{ORG_NAME} API",
    "DESCRIPTION": "Asset management REST API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "AssetStatusEnum": "apps.assets.models.Asset.Status",
        "HandoverStatusEnum": "apps.workflows.models.Handover.Status",
        "MaintenanceStatusEnum": "apps.maintenance.models.MaintenanceRecord.Status",
    },
}

# --- CORS / CSRF ------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --- Celery -----------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=f"{REDIS_URL}/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=f"{REDIS_URL}/0")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_RESULT_EXPIRES = 3600
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "warranty-expiry-alerts": {
        "task": "apps.notifications.tasks.check_warranty_expiry",
        "schedule": crontab(hour=7, minute=0),
    },
    "maintenance-due-alerts": {
        "task": "apps.notifications.tasks.check_maintenance_due",
        "schedule": crontab(hour=7, minute=10),
    },
    "scan-reminder-rules": {
        "task": "apps.reminders.tasks.scan_reminder_rules",
        "schedule": crontab(minute="*/5"),
    },
    "purge-reminder-files": {
        "task": "apps.reminders.tasks.purge_reminder_files",
        "schedule": crontab(hour=3, minute=30),
    },
    "overdue-return-alerts": {
        "task": "apps.notifications.tasks.check_overdue_returns",
        "schedule": crontab(hour=7, minute=20),
    },
}
WARRANTY_ALERT_DAYS = env.list("WARRANTY_ALERT_DAYS", cast=int, default=[30, 7, 0])
MAINTENANCE_ALERT_DAYS = env.int("MAINTENANCE_ALERT_DAYS", default=7)

# --- Logging ----------------------------------------------------------------
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOG_FORMAT = env("LOG_FORMAT", default="text")  # "json" in production
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_context": {"()": "apps.core.logging.RequestContextFilter"}},
    "formatters": {
        "text": {"format": "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s"},
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
            "rename_fields": {"asctime": "ts", "levelname": "level"},
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT,
            "filters": ["request_context"],
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "django.security": {"level": "WARNING", "propagate": True},
        "celery": {"level": LOG_LEVEL},
    },
}

# --- Email / SMS (reminders) ------------------------------------------------------
# Secrets come from the environment only; they are never stored in the DB or returned by the API.
SMTP_HOST = env("SMTP_HOST", default="")
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend" if SMTP_HOST else "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = SMTP_HOST
EMAIL_PORT = env.int("SMTP_PORT", default=587)
EMAIL_HOST_USER = env("SMTP_USER", default="")
EMAIL_HOST_PASSWORD = env("SMTP_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("SMTP_USE_TLS", default=EMAIL_PORT == 587)
EMAIL_USE_SSL = env.bool("SMTP_USE_SSL", default=EMAIL_PORT == 465)
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="assets@localhost")
SMS_PROVIDER = env("SMS_PROVIDER", default="console")
SMS_API_KEY = env("SMS_API_KEY", default="")
SMS_SENDER_ID = env("SMS_SENDER_ID", default="")
REMINDER_ATTACHMENT_MAX_MB = env.int("REMINDER_ATTACHMENT_MAX_MB", default=10)
REMINDER_LINK_HOURS = env.int("REMINDER_LINK_HOURS", default=72)
