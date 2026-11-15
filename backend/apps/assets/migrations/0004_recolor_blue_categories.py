from django.db import migrations

BLUE_TO_GREEN = {"#22d3ee": "#10b981", "#38bdf8": "#84cc16", "#60a5fa": "#22c55e", "#818cf8": "#65a30d"}


def forwards(apps, schema_editor):
    Category = apps.get_model("assets", "Category")
    for old, new in BLUE_TO_GREEN.items():
        Category.objects.filter(color__iexact=old).update(color=new)


class Migration(migrations.Migration):
    dependencies = [("assets", "0003_green_default_color")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
