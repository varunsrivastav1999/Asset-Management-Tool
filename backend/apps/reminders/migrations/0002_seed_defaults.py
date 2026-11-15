from django.db import migrations

TEMPLATES = {
    "Warranty expiry": (
        "Warranty ending in {{days_left}} days: {{asset_tag}}",
        "Hello {{recipient_name}},\n\nThe warranty for {{asset_name}} ({{asset_tag}}) ends on {{due_date}} — {{days_left}} day(s) from now.\nHolder: {{user_name}}\n\nReview it here: {{link}}",
        "Warranty for {{asset_tag}} {{asset_name}} ends {{due_date}} ({{days_left}}d).",
    ),
    "Maintenance due": (
        "Maintenance due {{due_date}}: {{asset_tag}}",
        "Hello {{recipient_name}},\n\n{{asset_name}} ({{asset_tag}}) is due for maintenance on {{due_date}}.\n\nDetails: {{link}}",
        "Maintenance due {{due_date}} for {{asset_tag}} {{asset_name}}.",
    ),
    "Overdue return": (
        "Overdue return: {{reference}}",
        "Hello {{recipient_name}},\n\n{{count}} asset(s) from handover {{reference}} were due back on {{due_date}} and haven't been returned yet.\n\nPlease arrange the return: {{link}}",
        "{{count}} asset(s) from {{reference}} were due back {{due_date}}.",
    ),
}


def seed(apps, schema_editor):
    Template = apps.get_model("reminders", "ReminderTemplate")
    Rule = apps.get_model("reminders", "ReminderRule")
    SidebarItem = apps.get_model("navigation", "SidebarItem")
    templates = {}
    for name, (subject, body, sms) in TEMPLATES.items():
        templates[name], _ = Template.objects.get_or_create(name=name, defaults={"subject": subject, "body": body, "sms_text": sms})
    assets = SidebarItem.objects.filter(item_type="page", table="assets").order_by("id").first()
    handovers = SidebarItem.objects.filter(item_type="page", table="handovers").order_by("id").first()
    daily = {"kind": "daily", "time": "09:00", "timezone": "UTC"}
    defaults = [
        ("Warranty expiry (30/7/1 days)", assets, "warranty_expiry", {"days": [30, 7, 1]}, ["holder", "managers"], "Warranty expiry"),
        ("Maintenance due (7 days)", assets, "maintenance_due", {"days": [7]}, ["holder", "managers"], "Maintenance due"),
        ("Overdue returns", handovers, "overdue_return", {}, ["holder", "department_head", "managers"], "Overdue return"),
    ]
    for name, section, trigger, cfg, types, tpl in defaults:
        Rule.objects.get_or_create(
            name=name,
            defaults={
                "section": section, "trigger": trigger, "trigger_config": cfg, "channels": ["email", "in_app"],
                "recipients": {"types": types, "user_ids": [], "emails": [], "phones": []}, "schedule": daily,
                "template": templates[tpl], "attachments": [], "is_active": False,
            },
        )
    # "Reminders" menu entry under Workflows for admins and managers.
    if not SidebarItem.objects.filter(route="/reminders").exists():
        group = SidebarItem.objects.filter(item_type="group", name="Workflows", parent=None).first()
        last = SidebarItem.objects.filter(parent=group).order_by("-order").values_list("order", flat=True).first()
        SidebarItem.objects.create(
            name="Reminders", item_type="page", route="/reminders", icon="bell", parent=group,
            order=(last if last is not None else -1) + 1, visible_roles=["admin", "manager"],
        )


class Migration(migrations.Migration):
    dependencies = [("reminders", "0001_initial"), ("navigation", "0007_add_tables_menu_item")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
