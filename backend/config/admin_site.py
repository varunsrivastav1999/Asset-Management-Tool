from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig


class SuperuserAdminSite(AdminSite):
    """Django admin is kept as a break-glass tool, restricted to active superusers.

    Day-to-day management happens in the app; nginx additionally IP-restricts /admin/ in production.
    """

    site_header = "Asset Management Tools — administration"
    site_title = "Asset admin"
    index_title = "Data administration"

    def has_permission(self, request):
        user = request.user
        return bool(user and user.is_active and user.is_superuser)


class SuperuserAdminConfig(AdminConfig):
    default_site = "config.admin_site.SuperuserAdminSite"
