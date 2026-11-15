from .base import *  # noqa: F401,F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
TRUSTED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=["http://localhost:2025", "http://127.0.0.1:2025"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["http://localhost:2025", "http://127.0.0.1:2025"])
JWT_REFRESH_COOKIE["secure"] = env.bool("JWT_COOKIE_SECURE", default=False)  # noqa: F405
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]
