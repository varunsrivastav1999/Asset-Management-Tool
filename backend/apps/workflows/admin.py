from django.contrib import admin

from .models import GoodsReceipt, Handover, HandoverItem


class HandoverItemInline(admin.TabularInline):
    model = HandoverItem
    extra = 0
    raw_id_fields = ("asset",)


@admin.register(Handover)
class HandoverAdmin(admin.ModelAdmin):
    list_display = ("reference", "type", "status", "to_user", "from_user", "created_at")
    list_filter = ("type", "status")
    search_fields = ("reference",)
    exclude = ("signature", "issuer_signature")
    inlines = [HandoverItemInline]


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ("reference", "vendor", "received_date", "received_by")
    search_fields = ("reference", "invoice_number")
    exclude = ("signature",)


@admin.register(HandoverItem)
class HandoverItemAdmin(admin.ModelAdmin):
    list_display = ("handover", "asset", "condition")
    raw_id_fields = ("handover", "asset")
