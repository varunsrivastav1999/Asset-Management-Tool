from django.contrib import admin

from .models import Asset, AssetEvent, AssetPhoto, Category, CustomField, Location, Vendor


class CustomFieldInline(admin.TabularInline):
    model = CustomField
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_active")
    search_fields = ("name",)
    inlines = [CustomFieldInline]


class PhotoInline(admin.TabularInline):
    model = AssetPhoto
    extra = 0


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("asset_tag", "name", "category", "status", "assigned_to", "warranty_expiry")
    list_filter = ("status", "condition", "category")
    search_fields = ("asset_tag", "name", "serial_number")
    raw_id_fields = ("assigned_to", "receipt", "created_by")
    readonly_fields = ("asset_tag",)
    inlines = [PhotoInline]


@admin.register(AssetEvent)
class AssetEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "asset", "event_type", "actor")
    list_filter = ("event_type",)
    raw_id_fields = ("asset",)


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "parent", "is_active")
    search_fields = ("name", "code")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_name", "email", "is_active")
    search_fields = ("name", "email")


@admin.register(CustomField)
class CustomFieldAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "category", "field_type", "required", "order")
    list_filter = ("field_type", "category")


@admin.register(AssetPhoto)
class AssetPhotoAdmin(admin.ModelAdmin):
    list_display = ("asset", "caption", "is_primary", "created_at")
    raw_id_fields = ("asset",)
