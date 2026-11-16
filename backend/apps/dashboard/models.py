from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.roles import default_roles


class DashboardWidget(TimeStampedModel):
    class Type(models.TextChoices):
        STAT = "stat", "Stat card"
        CHART = "chart", "Chart"
        TABLE = "table", "Table"

    class Size(models.TextChoices):
        SM = "sm", "Small (1/4)"
        MD = "md", "Medium (1/2)"
        LG = "lg", "Large (3/4)"
        FULL = "full", "Full width"

    title = models.CharField(max_length=80)
    widget_type = models.CharField("type", max_length=16, choices=Type.choices)
    data_source = models.CharField(max_length=120)  # registry key or table:<id>:<kind>[:<column>]
    chart_type = models.CharField(max_length=16, blank=True, help_text="doughnut | bar | hbar | line (charts only)")
    size = models.CharField(max_length=8, choices=Size.choices, default=Size.SM)
    position = models.PositiveIntegerField(default=0, db_index=True)
    visible_roles = models.JSONField(default=default_roles)
    config = models.JSONField(default=dict, blank=True, help_text='Optional display options, e.g. {"tone": "violet"}')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.title
