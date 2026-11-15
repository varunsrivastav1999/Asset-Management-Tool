from django.contrib import admin

from .models import ChannelConfig, ContactSettings, NotificationPreference, ReminderLog, ReminderRule, ReminderTemplate


@admin.register(ChannelConfig)
class ChannelConfigAdmin(admin.ModelAdmin):
    list_display = ("__str__", "email_enabled", "sms_enabled", "sms_provider", "daily_cap")


@admin.register(ReminderTemplate)
class ReminderTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "updated_at")
    search_fields = ("name", "subject")


@admin.register(ReminderRule)
class ReminderRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "trigger", "section", "is_active", "next_run_at", "last_run_at")
    list_filter = ("trigger", "is_active")
    search_fields = ("name",)


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "rule_name", "channel", "recipient_address", "status", "attempts")
    list_filter = ("status", "channel", "is_test")
    search_fields = ("recipient_address", "rule_name", "dedupe_key")
    readonly_fields = [f.name for f in ReminderLog._meta.fields]


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "section", "email_enabled", "sms_enabled")
    raw_id_fields = ("user",)


@admin.register(ContactSettings)
class ContactSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "verified_phone", "quiet_start", "quiet_end", "timezone")
    exclude = ("code_hash",)
    raw_id_fields = ("user",)
