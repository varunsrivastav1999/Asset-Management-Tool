from django.db import migrations


def forwards(apps, schema_editor):
    from apps.navigation.definitions import ensure_definition

    SidebarItem = apps.get_model("navigation", "SidebarItem")
    Definition = apps.get_model("navigation", "TableDefinition")
    for item in SidebarItem.objects.filter(item_type="page").exclude(table=""):
        defn = ensure_definition(item, Definition)
        if defn and defn.name != item.name:
            SidebarItem.objects.filter(pk=item.pk).update(name=defn.name)


class Migration(migrations.Migration):
    dependencies = [("navigation", "0005_table_definitions_records")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
