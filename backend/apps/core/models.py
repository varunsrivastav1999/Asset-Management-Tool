from django.db import models, transaction


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Counter(models.Model):
    """Row-locked, gap-free counters used for human-readable references (AST-000042)."""

    key = models.CharField(max_length=32, primary_key=True)
    value = models.PositiveBigIntegerField(default=0)

    def __str__(self):
        return f"{self.key}={self.value}"

    @classmethod
    def next(cls, key: str) -> int:
        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(key=key)
            counter.value += 1
            counter.save(update_fields=["value"])
            return counter.value


def next_reference(prefix: str, width: int = 6) -> str:
    return f"{prefix}-{Counter.next(prefix):0{width}d}"
