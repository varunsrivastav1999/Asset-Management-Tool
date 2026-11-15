from django.apps import AppConfig


class NavigationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.navigation"
    label = "navigation"

    def ready(self):
        from . import signals  # noqa: F401
