from rest_framework import serializers

from apps.core.roles import validate_roles

from .models import DashboardWidget
from .sources import CHART_TYPES, allowed_roles, source_meta

TONES = {"accent", "violet", "amber", "rose", "emerald"}


class DashboardWidgetSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(source="widget_type", choices=DashboardWidget.Type.choices)

    class Meta:
        model = DashboardWidget
        fields = [
            "id",
            "title",
            "type",
            "data_source",
            "chart_type",
            "size",
            "position",
            "visible_roles",
            "config",
            "is_active",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Title is required.")
        return value

    def validate_visible_roles(self, value):
        return validate_roles(value)

    def validate_config(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Config must be an object.")
        allowed = {"tone", "icon", "limit"}
        unknown = set(value) - allowed
        if unknown:
            raise serializers.ValidationError(f"Unsupported option(s): {', '.join(sorted(unknown))}.")
        if "tone" in value and value["tone"] not in TONES:
            raise serializers.ValidationError(f"tone must be one of {', '.join(sorted(TONES))}.")
        if "icon" in value and (not isinstance(value["icon"], str) or len(value["icon"]) > 48):
            raise serializers.ValidationError("icon must be a short icon name.")
        return value

    def validate(self, attrs):
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        kind, source = get("widget_type"), get("data_source")
        errors = {}
        meta = source_meta(source)
        if meta is None:
            errors["data_source"] = "Unknown data source."
        elif kind not in meta["types"]:
            errors["data_source"] = f"'{meta['label']}' can't be shown as a {kind} widget."
        if kind == DashboardWidget.Type.CHART and meta:
            chart = get("chart_type") or (meta.get("charts") or ["bar"])[0]
            if chart not in CHART_TYPES or (meta.get("charts") and chart not in meta["charts"]):
                errors["chart_type"] = f"Choose one of: {', '.join(meta.get('charts') or CHART_TYPES)}."
            attrs["chart_type"] = chart
        elif kind != DashboardWidget.Type.CHART:
            attrs["chart_type"] = ""
        roles = get("visible_roles") or []
        if meta and roles:
            forbidden = [r for r in roles if r not in allowed_roles(source)]
            if forbidden:
                why = "comes from a table they can't see" if meta["scope"] == "table" else "contains organisation-wide data"
                errors["visible_roles"] = f"'{meta['label']}' {why}, so it can't be shown to: {', '.join(forbidden)}."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class WidgetReorderSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
