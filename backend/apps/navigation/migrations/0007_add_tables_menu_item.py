from django.db import migrations


def forwards(apps, schema_editor):
    SidebarItem = apps.get_model("navigation", "SidebarItem")
    if SidebarItem.objects.filter(route="/settings/tables").exists():
        return
    settings_group = SidebarItem.objects.filter(item_type="group", name="Settings", parent=None).first()
    last = SidebarItem.objects.filter(parent=settings_group).order_by("-order").values_list("order", flat=True).first()
    SidebarItem.objects.create(
        name="Tables",
        item_type="page",
        route="/settings/tables",
        icon="list",
        parent=settings_group,
        order=(last if last is not None else -1) + 1,
        visible_roles=["admin"],
    )


class Migration(migrations.Migration):
    dependencies = [("navigation", "0006_seed_table_definitions")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
