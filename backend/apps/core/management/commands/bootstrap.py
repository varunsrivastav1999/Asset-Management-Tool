import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

# First-run admin when ADMIN_EMAIL / ADMIN_PASSWORD aren't set. The password is flagged for change at first sign-in.
DEFAULT_ADMIN_EMAIL = "admin@gmail.com"
DEFAULT_ADMIN_PASSWORD = "admin"


class Command(BaseCommand):
    help = "Idempotent first-run setup: default menu, tables, columns and widgets; on a fresh database also the first admin."

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

        self._first_admin()

    def _first_admin(self):
        """Create the first admin once, on a fresh database. Never touches existing accounts or passwords."""
        User = get_user_model()
        if User.objects.filter(Q(is_superuser=True) | Q(role="admin")).exists():
            return  # not a fresh database: an admin already exists
        email = (os.environ.get("ADMIN_EMAIL") or DEFAULT_ADMIN_EMAIL).strip().lower()
        password = os.environ.get("ADMIN_PASSWORD")
        generated = password == ""  # explicitly empty: generate a random one
        if password is None:
            password = DEFAULT_ADMIN_PASSWORD
        if generated:
            password = secrets.token_urlsafe(12)
        user = User.objects.create_superuser(email=email, password=password, first_name="Admin", last_name="User")
        # A well-known or printed password must be replaced: the app keeps reminding until it is.
        user.must_change_password = generated or password == DEFAULT_ADMIN_PASSWORD
        user.save(update_fields=["must_change_password"])
        self.stdout.write(self.style.SUCCESS(f"Created the first admin: {email}"))
        if generated:
            self.stdout.write(self.style.WARNING(f"Generated admin password: {password}  (change it after signing in)"))
        elif user.must_change_password:
            self.stdout.write(self.style.WARNING("The admin uses the default password — change it after signing in."))
