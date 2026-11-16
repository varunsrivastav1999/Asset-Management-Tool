from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.accounts.views import DepartmentViewSet, UserViewSet
from apps.assets.views import AssetViewSet, CategoryViewSet, LocationViewSet, MyAssetsViewSet, VendorViewSet
from apps.audit.api import AuditLogViewSet
from apps.core.views import BackupFileView, BackupsView, BackupUploadView, app_config, liveness, readiness
from apps.dashboard.api import DashboardWidgetViewSet, dashboard
from apps.dashboard.views import stats
from apps.maintenance.views import MaintenanceViewSet
from apps.navigation.column_views import TableColumnViewSet, table_columns, table_prefs, tables
from apps.navigation.definition_views import TableDefinitionViewSet, TableRecordViewSet
from apps.navigation.media_views import TableMediaFileView, TableMediaUploadView
from apps.navigation.views import SidebarItemViewSet, sidebar
from apps.notifications.views import NotificationViewSet
from apps.workflows.views import GoodsReceiptViewSet, HandoverViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("departments", DepartmentViewSet, basename="department")
router.register("categories", CategoryViewSet, basename="category")
router.register("locations", LocationViewSet, basename="location")
router.register("vendors", VendorViewSet, basename="vendor")
router.register("assets", AssetViewSet, basename="asset")
router.register("my-assets", MyAssetsViewSet, basename="my-asset")
router.register("receipts", GoodsReceiptViewSet, basename="receipt")
router.register("handovers", HandoverViewSet, basename="handover")
router.register("maintenance", MaintenanceViewSet, basename="maintenance")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")
router.register("sidebar-items", SidebarItemViewSet, basename="sidebar-item")
router.register("dashboard-widgets", DashboardWidgetViewSet, basename="dashboard-widget")
router.register("table-columns", TableColumnViewSet, basename="table-column")
router.register("table-definitions", TableDefinitionViewSet, basename="table-definition")
router.register("records", TableRecordViewSet, basename="record")

api = [
    path("health/", liveness, name="health"),
    path("health/ready/", readiness, name="health-ready"),
    path("app-config/", app_config, name="app-config"),
    path("backups/", BackupsView.as_view(), name="backups"),
    path("backups/upload/", BackupUploadView.as_view(), name="backup-upload"),
    path("backups/<str:name>/", BackupFileView.as_view(), name="backup-file"),
    path("auth/", include("apps.accounts.urls")),
    path("dashboard/", dashboard, name="dashboard"),
    path("dashboard/stats/", stats, name="dashboard-stats"),
    path("sidebar/", sidebar, name="sidebar"),
    path("reminders/", include("apps.reminders.urls")),
    path("tables/", tables, name="tables"),
    path("tables/prefs/", table_prefs, name="table-prefs"),
    path("table-media/", TableMediaUploadView.as_view(), name="table-media"),
    path("table-media/<uuid:pk>/", TableMediaFileView.as_view(), name="table-media-file"),
    path("tables/<slug:table>/columns/", table_columns, name="table-columns-config"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("", include(router.urls)),
]

urlpatterns = [
    path(f"{settings.ADMIN_URL}", admin.site.urls),
    path("api/", include(api)),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
