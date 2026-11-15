import re

from rest_framework import serializers

from apps.core.roles import validate_roles

from .models import SidebarItem

ICON_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
ROUTE_RE = re.compile(r"^/(?!/)[A-Za-z0-9\-._~/?=&%:+]*$")
MAX_DEPTH = 3


class SidebarItemSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(source="item_type", choices=SidebarItem.Type.choices)

    class Meta:
        model = SidebarItem
        fields = [
            "id",
            "name",
            "type",
            "icon",
            "route",
            "url",
            "open_in_new_tab",
            "parent",
            "order",
            "visible_roles",
            "is_active",
            "color",
            "icon_color",
            "active_color",
            "gradient",
            "glow",
            "table",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_table(self, value):
        from .tables import TABLES

        if value and value not in TABLES:
            raise serializers.ValidationError("Unknown table.")
        return value

    def validate_visible_roles(self, value):
        return validate_roles(value)

    def validate_icon(self, value):
        value = (value or "").strip()
        if value and not ICON_RE.match(value):
            raise serializers.ValidationError("Use a lowercase icon name such as 'layout-dashboard'.")
        return value

    def validate_parent(self, parent):
        if parent is None:
            return parent
        if parent.item_type != SidebarItem.Type.GROUP:
            raise serializers.ValidationError("Items can only be nested inside a group.")
        depth, node, seen = 1, parent, set()
        while node is not None:
            if self.instance and node.pk == self.instance.pk:
                raise serializers.ValidationError("An item cannot be nested inside itself.")
            if node.pk in seen:
                break
            seen.add(node.pk)
            node = node.parent
            depth += 1
        if depth > MAX_DEPTH:
            raise serializers.ValidationError(f"Groups can be nested at most {MAX_DEPTH} levels deep.")
        return parent

    def validate(self, attrs):
        get = lambda k, default="": attrs.get(k, getattr(self.instance, k, default) if self.instance else default)  # noqa: E731
        kind = get("item_type", SidebarItem.Type.PAGE)
        name = (get("name") or "").strip()
        route = (get("route") or "").strip()
        url = (get("url") or "").strip()
        errors = {}
        if kind != SidebarItem.Type.DIVIDER and not name:
            errors["name"] = "Name is required."
        if kind == SidebarItem.Type.PAGE:
            if not route or not ROUTE_RE.match(route):
                errors["route"] = "Enter an in-app path starting with '/', e.g. /assets."
            attrs["url"] = ""
            # Pages that show a known table get its column config automatically.
            if not get("table"):
                from .tables import table_for_route

                attrs["table"] = table_for_route(route)
        elif kind == SidebarItem.Type.LINK:
            if not url.lower().startswith(("https://", "http://")):
                errors["url"] = "Links must be absolute http(s) URLs."
            attrs["route"] = ""
            attrs["table"] = ""
        else:
            attrs["route"] = ""
            attrs["url"] = ""
            attrs["table"] = ""
            if kind == SidebarItem.Type.DIVIDER:
                attrs["icon"] = ""
        if self.instance and kind != SidebarItem.Type.GROUP and self.instance.children.exists():
            errors["type"] = "Move or delete this group's items before changing its type."
        if errors:
            raise serializers.ValidationError(errors)
        attrs["name"] = name
        if self.instance is not None:
            from .definitions import definition_of

            defn = definition_of(self.instance)
            if defn is not None:
                if attrs.get("table", self.instance.table) != self.instance.table or kind != SidebarItem.Type.PAGE:
                    raise serializers.ValidationError(
                        {"table": "This page owns a table — delete the table instead of changing it."}
                    )
                clash = type(defn).objects.filter(name__iexact=name).exclude(pk=defn.pk).exists()
                if clash:
                    raise serializers.ValidationError({"name": "A table with this name already exists."})
        return attrs

    def update(self, instance, validated_data):
        item = super().update(instance, validated_data)
        from .definitions import definition_of

        defn = definition_of(item)
        if defn is not None and (defn.name != item.name or (item.icon and defn.icon != item.icon)):
            type(defn).objects.filter(pk=defn.pk).update(name=item.name, icon=item.icon or defn.icon)
        return item


class ReorderEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    parent = serializers.IntegerField(allow_null=True, required=False)
    order = serializers.IntegerField(min_value=0)


class ReorderSerializer(serializers.Serializer):
    items = ReorderEntrySerializer(many=True, allow_empty=False)
