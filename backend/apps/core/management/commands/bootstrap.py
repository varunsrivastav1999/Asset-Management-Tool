import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Idempotent first-run setup: default sidebar/columns/tables/widgets and the first admin (ADMIN_EMAIL / ADMIN_PASSWORD)."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.dashboard.defaults import seed_widgets
        from apps.dashboard.models import DashboardWidget
        from apps.navigation.defaults import seed_sidebar
        from apps.navigation.definitions import ensure_definition
        from apps.navigation.models import SidebarItem
        from apps.navigation.tables import ensure_columns

        seed_sidebar(SidebarItem)
        seed_widgets(DashboardWidget)
        for item in SidebarItem.objects.filter(item_type="page").exclude(table=""):
            ensure_definition(item)
            ensure_columns(item)

        User = get_user_model()
        email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
        if not email:
            if not User.objects.filter(is_superuser=True).exists():
                self.stdout.write(
                    self.style.WARNING("No ADMIN_EMAIL set and no superuser exists — run `manage.py createsuperuser`.")
                )
            return
        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write(f"Admin {email} already exists.")
            return
        password = os.environ.get("ADMIN_PASSWORD") or ""
        generated = not password
        if generated:
            password = secrets.token_urlsafe(12)
        User.objects.create_superuser(email=email, password=password, first_name="Admin", last_name="User")
        self.stdout.write(self.style.SUCCESS(f"Created admin {email}."))
        if generated:
            # Printed once so a fresh `docker compose up` needs no manual step; change it after first login.
            self.stdout.write(
                self.style.WARNING(f"Generated admin password: {password}  (set ADMIN_PASSWORD to choose your own)")
            )
