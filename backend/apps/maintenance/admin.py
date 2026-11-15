from django.contrib import admin

from .models import MaintenanceRecord


@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = ("asset", "title", "kind", "status", "scheduled_date", "completed_date", "cost")
    list_filter = ("status", "kind")
    raw_id_fields = ("asset",)
