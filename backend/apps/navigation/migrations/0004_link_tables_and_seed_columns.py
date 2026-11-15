from django.db import migrations


def forwards(apps, schema_editor):
    from apps.navigation.defaults import ROUTE_TABLES
    from apps.navigation.tables import ensure_columns

    SidebarItem = apps.get_model("navigation", "SidebarItem")
    TableColumn = apps.get_model("navigation", "TableColumn")
    for item in SidebarItem.objects.filter(item_type="page"):
        if not item.table:
            item.table = ROUTE_TABLES.get((item.route or "").split("?")[0], "")
            if item.table:
                item.save(update_fields=["table"])
        if item.table:
            ensure_columns(item, model=TableColumn)


class Migration(migrations.Migration):
    dependencies = [("navigation", "0003_sidebaritem_active_color_sidebaritem_color_and_more")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
