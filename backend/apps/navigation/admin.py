from django.contrib import admin

from .models import SidebarItem, TableColumn, TableDefinition, TablePreference, TableRecord


class TableColumnInline(admin.TabularInline):
    model = TableColumn
    extra = 0
    fields = ("order", "name", "key", "column_type", "is_visible", "is_required", "is_searchable", "is_sortable", "visible_roles")
    readonly_fields = ("key",)


@admin.register(SidebarItem)
class SidebarItemAdmin(admin.ModelAdmin):
    list_display = ("name", "item_type", "parent", "order", "route", "table", "color", "is_active")
    list_filter = ("item_type", "is_active", "table")
    list_editable = ("order", "is_active")
    search_fields = ("name", "route", "url")
    inlines = [TableColumnInline]


@admin.register(TableColumn)
class TableColumnAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "sidebar_item", "column_type", "order", "is_visible", "is_builtin")
    list_filter = ("column_type", "is_builtin", "sidebar_item")
    search_fields = ("name", "key")


@admin.register(TablePreference)
class TablePreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "sidebar_item", "updated_at")
    raw_id_fields = ("user",)


@admin.register(TableDefinition)
class TableDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "singular", "source", "slug", "sidebar_item")
    list_filter = ("source",)
    search_fields = ("name", "singular", "slug")


@admin.register(TableRecord)
class TableRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "definition", "is_archived", "archived_from", "created_at")
    list_filter = ("is_archived", "definition")
