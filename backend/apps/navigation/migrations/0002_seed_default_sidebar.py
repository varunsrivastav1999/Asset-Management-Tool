from django.db import migrations


def seed(apps, schema_editor):
    from apps.navigation.defaults import seed_sidebar

    seed_sidebar(apps.get_model("navigation", "SidebarItem"))


def unseed(apps, schema_editor):
    apps.get_model("navigation", "SidebarItem").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("navigation", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
