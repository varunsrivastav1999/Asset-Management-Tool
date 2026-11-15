from django.db import migrations


def forwards(apps, schema_editor):
    SidebarItem = apps.get_model("navigation", "SidebarItem")
    if SidebarItem.objects.filter(route="/settings/backups").exists():
        return
    settings_group = SidebarItem.objects.filter(item_type="group", name="Settings", parent=None).first()
    last = SidebarItem.objects.filter(parent=settings_group).order_by("-order").values_list("order", flat=True).first()
    SidebarItem.objects.create(
        name="Backups",
        item_type="page",
        route="/settings/backups",
        icon="hard-drive",
        parent=settings_group,
        order=(last if last is not None else -1) + 1,
        visible_roles=["admin"],
    )


class Migration(migrations.Migration):
    dependencies = [("navigation", "0008_alter_sidebaritem_active_color_and_more")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
