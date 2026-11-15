from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.notifications.services import broadcast_all

from .models import SidebarItem, TableColumn


def broadcast_sidebar_change():
    """Tell every connected client to refetch its (role-filtered) menu once the transaction commits."""
    transaction.on_commit(lambda: broadcast_all({"type": "sidebar.update"}))


@receiver(post_save, sender=SidebarItem, dispatch_uid="sidebar-save")
@receiver(post_delete, sender=SidebarItem, dispatch_uid="sidebar-delete")
def _sidebar_changed(sender, instance=None, created=False, **kwargs):
    if kwargs.get("signal") is post_save and instance is not None and instance.table and instance.table != "custom":
        from .definitions import ensure_definition

        ensure_definition(instance)
    broadcast_sidebar_change()


def broadcast_columns_change(item_id):
    transaction.on_commit(lambda: broadcast_all({"type": "table.columns", "item": item_id}))


@receiver(post_save, sender=TableColumn, dispatch_uid="column-save")
@receiver(post_delete, sender=TableColumn, dispatch_uid="column-delete")
def _column_changed(sender, instance, **kwargs):
    broadcast_columns_change(instance.sidebar_item_id)
