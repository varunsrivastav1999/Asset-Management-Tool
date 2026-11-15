from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import AuditedViewSetMixin, record
from apps.core.exceptions import DomainError
from apps.core.permissions import IsAdmin
from apps.core.roles import effective_role

from .defaults import seed_sidebar
from .definitions import definition_of, meta
from .models import SidebarItem
from .serializers import MAX_DEPTH, ReorderSerializer, SidebarItemSerializer
from .signals import broadcast_sidebar_change


def build_tree(items, role: str | None):
    """Nest items and drop anything the role cannot see (a hidden group hides its children).

    Groups left without visible children and redundant dividers are pruned so the menu never
    shows empty headings or stacked separators.
    """
    by_parent: dict[int | None, list[SidebarItem]] = {}
    for item in items:
        by_parent.setdefault(item.parent_id, []).append(item)

    def visible(item):
        return item.is_active and (role is None or role in (item.visible_roles or []))

    def walk(parent_id, depth):
        out = []
        for item in sorted(by_parent.get(parent_id, []), key=lambda i: (i.order, i.id)):
            if not visible(item) or depth > MAX_DEPTH:
                continue
            node = {
                "id": item.id,
                "name": item.name,
                "type": item.item_type,
                "icon": item.icon,
                "route": item.route,
                "url": item.url,
                "open_in_new_tab": item.open_in_new_tab,
                "color": item.color,
                "icon_color": item.icon_color,
                "active_color": item.active_color,
                "gradient": item.gradient,
                "glow": item.glow,
                "table": item.table,
                "table_meta": meta(definition_of(item)),
            }
            if item.item_type == SidebarItem.Type.GROUP:
                node["children"] = walk(item.id, depth + 1)
                if role is not None and not node["children"]:
                    continue
            out.append(node)
        # Trim leading/trailing/consecutive dividers.
        cleaned = []
        for node in out:
            if node["type"] == "divider" and (not cleaned or cleaned[-1]["type"] == "divider"):
                continue
            cleaned.append(node)
        while cleaned and cleaned[-1]["type"] == "divider":
            cleaned.pop()
        return cleaned

    return walk(None, 1)


@extend_schema(responses={200: dict})
@api_view(["GET"])
def sidebar(request):
    """The current user's navigation menu (role-filtered tree)."""
    items = list(SidebarItem.objects.select_related("definition"))
    return Response({"items": build_tree(items, effective_role(request.user))})


class SidebarItemViewSet(AuditedViewSetMixin, viewsets.ModelViewSet):
    """Admin-only management of sidebar items (flat list; use `parent` + `order` for structure)."""

    queryset = SidebarItem.objects.select_related("parent").order_by("parent_id", "order", "id")
    serializer_class = SidebarItemSerializer
    permission_classes = [IsAdmin]
    pagination_class = None
    filterset_fields = ["parent", "item_type", "is_active"]
    search_fields = ["name", "route", "url"]

    def perform_destroy(self, instance):
        # Pages that own a table follow the table's deletion rules (no deleting live data).
        from .definition_views import delete_blocker

        stack, owned = [instance], []
        while stack:
            node = stack.pop()
            defn = definition_of(node)
            if defn:
                owned.append(defn)
            stack.extend(node.children.all())
        owned_ids = [d.pk for d in owned]
        for defn in owned:
            blocker = delete_blocker(defn, deleting=owned_ids)
            if blocker:
                raise DomainError(blocker, code="has_data")
        for defn in owned:
            defn.records.update(archived_from=defn.name, is_archived=True)
        count = instance.children.count()
        super().perform_destroy(instance)
        if count:
            record(
                AuditLog.Action.DELETE,
                self.request.user,
                model="navigation.sidebaritem",
                object_repr=f"{count} nested item(s) of {instance}",
            )

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def tree(self, request):
        """Full tree including hidden/inactive items, for the settings screen."""
        items = list(SidebarItem.objects.all())

        def walk(parent_id):
            nodes = []
            for item in sorted((i for i in items if i.parent_id == parent_id), key=lambda i: (i.order, i.id)):
                data = SidebarItemSerializer(item).data
                if item.item_type == SidebarItem.Type.GROUP:
                    data["children"] = walk(item.id)
                nodes.append(data)
            return nodes

        return Response({"items": walk(None)})

    @extend_schema(request=ReorderSerializer, responses={200: dict})
    @action(detail=False, methods=["post"])
    def reorder(self, request):
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries = serializer.validated_data["items"]
        with transaction.atomic():
            items = {i.pk: i for i in SidebarItem.objects.select_for_update()}
            ids = [e["id"] for e in entries]
            if len(ids) != len(set(ids)):
                raise DomainError("Each item may appear only once.", field="items")
            missing = [i for i in ids if i not in items]
            if missing:
                raise DomainError(f"Unknown item id(s): {missing}.", field="items")
            new_parent = {pk: item.parent_id for pk, item in items.items()}
            for e in entries:
                parent = e.get("parent")
                if parent is not None and (parent not in items or items[parent].item_type != SidebarItem.Type.GROUP):
                    raise DomainError("Items can only be placed inside groups.", field="items")
                new_parent[e["id"]] = parent
            # Reject cycles and over-deep nesting in the resulting structure.
            for pk in items:
                depth, node, seen = 1, new_parent[pk], {pk}
                while node is not None:
                    if node in seen:
                        raise DomainError("That arrangement would nest a group inside itself.", field="items")
                    seen.add(node)
                    node = new_parent.get(node)
                    depth += 1
                if depth > MAX_DEPTH + 1:
                    raise DomainError(f"Groups can be nested at most {MAX_DEPTH} levels deep.", field="items")
            changed = []
            for e in entries:
                item = items[e["id"]]
                item.parent_id = e.get("parent")
                item.order = e["order"]
                changed.append(item)
            SidebarItem.objects.bulk_update(changed, ["parent", "order"])
        record(
            AuditLog.Action.BULK_UPDATE,
            request.user,
            model="navigation.sidebaritem",
            object_repr=f"Reordered {len(changed)} sidebar items",
            changes={"items": entries},
        )
        broadcast_sidebar_change()
        return Response({"updated": len(changed)})

    @extend_schema(request=None, responses={200: dict})
    @action(detail=False, methods=["post"])
    def reset(self, request):
        from .definitions import ensure_definition
        from .tables import ensure_columns

        with transaction.atomic():
            created = seed_sidebar(SidebarItem, replace=True)
            # Same end state as a first start: every table page has its definition and column setup.
            for item in SidebarItem.objects.filter(item_type=SidebarItem.Type.PAGE).exclude(table=""):
                ensure_definition(item)
                ensure_columns(item)
        record(AuditLog.Action.BULK_UPDATE, request.user, model="navigation.sidebaritem", object_repr="Sidebar reset to defaults")
        broadcast_sidebar_change()
        return Response({"created": created}, status=status.HTTP_200_OK)
