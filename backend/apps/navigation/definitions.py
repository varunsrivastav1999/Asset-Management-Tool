"""Helpers for TableDefinition (the editable identity of a table page)."""

from django.utils.text import slugify

from .tables import SINGULAR, TABLES


def definition_of(item):
    """The item's TableDefinition or None (works with prefetched/select_related items)."""
    try:
        return item.definition
    except Exception:  # noqa: BLE001 - RelatedObjectDoesNotExist differs between real and historical models
        return None


def unique_name(Definition, base: str, exclude_pk=None) -> str:
    name, i = base, 2
    qs = Definition.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(name__iexact=name).exists():
        name, i = f"{base} {i}", i + 1
    return name


def unique_slug(Definition, base: str, exclude_pk=None) -> str:
    root = slugify(base)[:70] or "table"
    slug, i = root, 2
    qs = Definition.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(slug=slug).exists():
        slug, i = f"{root}-{i}", i + 1
    return slug


def ensure_definition(item, Definition=None):
    """Create the definition for a built-in table page if missing (custom tables are created explicitly)."""
    if Definition is None:
        from .models import TableDefinition as Definition
    if item.item_type != "page" or not item.table or item.table == "custom" or item.table not in TABLES:
        return None
    existing = Definition.objects.filter(sidebar_item_id=item.pk).first()
    if existing:
        return existing
    name = unique_name(Definition, item.name or TABLES[item.table].label)
    return Definition.objects.create(
        sidebar_item_id=item.pk,
        source=item.table,
        slug=unique_slug(Definition, name),
        name=name,
        singular=SINGULAR.get(item.table, name),
        icon=item.icon or "",
    )


def meta(defn) -> dict | None:
    if defn is None:
        return None
    return {
        "id": defn.pk,
        "name": defn.name,
        "singular": defn.singular,
        "icon": defn.icon,
        "description": defn.description,
        "slug": defn.slug,
        "source": defn.source,
    }
