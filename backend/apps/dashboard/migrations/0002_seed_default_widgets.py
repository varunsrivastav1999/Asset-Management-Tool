from django.db import migrations


def seed(apps, schema_editor):
    from apps.dashboard.defaults import seed_widgets

    seed_widgets(apps.get_model("dashboard", "DashboardWidget"))


def unseed(apps, schema_editor):
    apps.get_model("dashboard", "DashboardWidget").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
