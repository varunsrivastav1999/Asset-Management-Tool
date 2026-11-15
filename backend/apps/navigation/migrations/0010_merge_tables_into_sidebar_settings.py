from django.db import migrations


def forwards(apps, schema_editor):
    """Tables are managed on the Sidebar screen now: drop the separate menu entry and rename the Sidebar one."""
    SidebarItem = apps.get_model("navigation", "SidebarItem")
    SidebarItem.objects.filter(route="/settings/tables", item_type="page").delete()
    SidebarItem.objects.filter(route="/settings/sidebar", item_type="page", name="Sidebar").update(name="Sidebar & tables")


def backwards(apps, schema_editor):
    SidebarItem = apps.get_model("navigation", "SidebarItem")
    SidebarItem.objects.filter(route="/settings/sidebar", item_type="page", name="Sidebar & tables").update(name="Sidebar")


class Migration(migrations.Migration):
    dependencies = [("navigation", "0009_add_backups_menu_item")]

    operations = [migrations.RunPython(forwards, backwards)]
