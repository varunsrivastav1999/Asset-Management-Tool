import datetime

from celery import shared_task
from django.utils import timezone

from .models import TableMedia, TableRecord
from .tables import model_for


def is_referenced(media: TableMedia) -> bool:
    """Whether any row of the media's table still points at it."""
    item = media.sidebar_item
    lookup = {f"custom_data__{media.column_key}__id": str(media.pk)}
    if item.table == "custom":
        return TableRecord.objects.filter(definition__sidebar_item=item, **lookup).exists()
    model = model_for(item.table)
    return bool(model and model.objects.filter(**lookup).exists())


@shared_task
def purge_orphan_table_media(min_age_hours: int = 24) -> int:
    """Delete uploads no cell refers to any more (replaced, cleared, or never saved). Grace period for in-progress edits."""
    cutoff = timezone.now() - datetime.timedelta(hours=min_age_hours)
    removed = 0
    for media in TableMedia.objects.filter(created_at__lt=cutoff).select_related("sidebar_item").iterator():
        if not is_referenced(media):
            media.delete()  # the file goes with it (post_delete signal)
            removed += 1
    return removed
