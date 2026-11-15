from django.contrib import admin

from .models import DashboardWidget


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display = ("title", "widget_type", "data_source", "chart_type", "size", "position", "is_active")
    list_filter = ("widget_type", "size", "is_active")
    list_editable = ("position", "is_active")
