import datetime

import django_filters
from django.db.models import Q

from .models import Asset, Category


class CharInFilter(django_filters.BaseInFilter, django_filters.CharFilter):
    pass


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    pass


class AssetFilter(django_filters.FilterSet):
    status = CharInFilter(field_name="status", lookup_expr="in")
    condition = CharInFilter(field_name="condition", lookup_expr="in")
    category = django_filters.NumberFilter(method="filter_category")
    department = NumberInFilter(field_name="department", lookup_expr="in")
    location = NumberInFilter(field_name="location", lookup_expr="in")
    vendor = NumberInFilter(field_name="vendor", lookup_expr="in")
    assigned_to = django_filters.NumberFilter(field_name="assigned_to")
    receipt = django_filters.NumberFilter(field_name="receipt")
    purchased_after = django_filters.DateFilter(field_name="purchase_date", lookup_expr="gte")
    purchased_before = django_filters.DateFilter(field_name="purchase_date", lookup_expr="lte")
    warranty_expiring_in = django_filters.NumberFilter(method="filter_warranty_expiring")
    warranty_expired = django_filters.BooleanFilter(method="filter_warranty_expired")
    maintenance_due_in = django_filters.NumberFilter(method="filter_maintenance_due")
    unassigned = django_filters.BooleanFilter(method="filter_unassigned")

    class Meta:
        model = Asset
        fields = []

    def filter_category(self, qs, name, value):
        try:
            category = Category.objects.get(pk=value)
        except Category.DoesNotExist:
            return qs.none()
        return qs.filter(category_id__in=category.descendant_ids())

    def filter_warranty_expiring(self, qs, name, value):
        today = datetime.date.today()
        return qs.filter(warranty_expiry__gte=today, warranty_expiry__lte=today + datetime.timedelta(days=int(value)))

    def filter_warranty_expired(self, qs, name, value):
        today = datetime.date.today()
        return (
            qs.filter(warranty_expiry__lt=today)
            if value
            else qs.filter(Q(warranty_expiry__gte=today) | Q(warranty_expiry__isnull=True))
        )

    def filter_maintenance_due(self, qs, name, value):
        limit = datetime.date.today() + datetime.timedelta(days=int(value))
        return qs.filter(next_maintenance_date__lte=limit).exclude(status=Asset.Status.RETIRED)

    def filter_unassigned(self, qs, name, value):
        cond = Q(assigned_to__isnull=True, department__isnull=True)
        return qs.filter(cond) if value else qs.exclude(cond)
