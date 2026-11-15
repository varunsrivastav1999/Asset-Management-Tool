from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.navigation.models import SidebarItem

from .models import ReminderRule


@receiver(pre_delete, sender=SidebarItem, dispatch_uid="reminders-section-deleted")
def _pause_rules_of_deleted_section(sender, instance, **kwargs):
    """A deleted menu section (and the table it showed) can't be reminded about: switch its rules off.

    The foreign key is SET_NULL so rules and their history survive, but an active rule without its section
    would otherwise keep running against nothing.
    """
    ReminderRule.objects.filter(section=instance, is_active=True).update(is_active=False, next_run_at=None)
