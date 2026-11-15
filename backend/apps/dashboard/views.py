import datetime

from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.assets.models import Asset, AssetEvent
from apps.assets.serializers import AssetEventSerializer
from apps.core.permissions import is_manager
from apps.maintenance.models import MaintenanceRecord
from apps.workflows.models import Handover

CACHE_KEY = "dashboard:stats:v1"
CACHE_TTL = 120


def _months(n=12):
    today = timezone.localdate().replace(day=1)
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append(datetime.date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def compute_stats() -> dict:
    today = timezone.localdate()
    active = Asset.objects.exclude(status=Asset.Status.RETIRED)
    by_status = dict(Asset.objects.values_list("status").annotate(c=Count("id")).values_list("status", "c"))
    totals = active.aggregate(value=Sum("purchase_cost"), count=Count("id"))

    by_category = list(
        Asset.objects.values("category__name", "category__color")
        .annotate(count=Count("id"), value=Sum("purchase_cost"))
        .order_by("-count")[:8]
    )
    by_department = list(
        Asset.objects.filter(department__isnull=False)
        .values("department__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:8]
    )
    months = _months(12)
    start = months[0]
    added = dict(
        Asset.objects.filter(created_at__date__gte=start)
        .annotate(m=TruncMonth("created_at"))
        .values("m")
        .annotate(c=Count("id"))
        .values_list("m", "c")
    )
    handovers = (
        Handover.objects.filter(status=Handover.Status.COMPLETED, completed_at__date__gte=start)
        .annotate(m=TruncMonth("completed_at"))
        .values("m", "type")
        .annotate(c=Count("id"))
    )
    ho = {}
    for row in handovers:
        ho.setdefault(row["m"].date() if hasattr(row["m"], "date") else row["m"], {})[row["type"]] = row["c"]

    def _key(d):
        return d.date() if hasattr(d, "date") else d

    added = {_key(k): v for k, v in added.items()}
    timeline = [
        {
            "month": m.strftime("%Y-%m"),
            "added": added.get(m, 0),
            "issued": ho.get(m, {}).get("issue", 0),
            "returned": ho.get(m, {}).get("return", 0),
            "transferred": ho.get(m, {}).get("transfer", 0),
        }
        for m in months
    ]
    warranty = Asset.objects.exclude(status__in=[Asset.Status.RETIRED, Asset.Status.LOST]).filter(warranty_expiry__isnull=False)
    warranty_buckets = {
        "expired": warranty.filter(warranty_expiry__lt=today).count(),
        "d30": warranty.filter(warranty_expiry__gte=today, warranty_expiry__lte=today + datetime.timedelta(days=30)).count(),
        "d90": warranty.filter(
            warranty_expiry__gt=today + datetime.timedelta(days=30), warranty_expiry__lte=today + datetime.timedelta(days=90)
        ).count(),
    }
    expiring_soon = list(
        warranty.filter(warranty_expiry__gte=today, warranty_expiry__lte=today + datetime.timedelta(days=60))
        .order_by("warranty_expiry")
        .values("id", "asset_tag", "name", "warranty_expiry")[:6]
    )
    maintenance_due = list(
        active.filter(next_maintenance_date__isnull=False, next_maintenance_date__lte=today + datetime.timedelta(days=14))
        .exclude(status=Asset.Status.LOST)
        .order_by("next_maintenance_date")
        .values("id", "asset_tag", "name", "next_maintenance_date", "status")[:6]
    )
    open_maintenance = MaintenanceRecord.objects.filter(
        status__in=[MaintenanceRecord.Status.SCHEDULED, MaintenanceRecord.Status.IN_PROGRESS]
    ).count()
    events = AssetEvent.objects.select_related(
        "asset",
        "actor",
        "to_user",
        "from_user",
        "to_department",
        "from_department",
        "to_location",
        "from_location",
        "handover",
        "receipt",
    )[:10]
    recent = []
    for e, data in zip(events, AssetEventSerializer(events, many=True).data, strict=True):
        data["asset_tag"], data["asset_name"], data["asset_id"] = e.asset.asset_tag, e.asset.name, e.asset_id
        recent.append(data)

    utilization = 0.0
    usable = sum(by_status.get(s, 0) for s in (Asset.Status.IN_STOCK, Asset.Status.ASSIGNED, Asset.Status.IN_REPAIR))
    if usable:
        utilization = round(by_status.get(Asset.Status.ASSIGNED, 0) / usable * 100, 1)

    return {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "totals": {
            "assets": sum(by_status.values()),
            "active": totals["count"] or 0,
            "value": str(totals["value"] or 0),
            "utilization": utilization,
            "pending_handovers": Handover.objects.filter(status=Handover.Status.PENDING).count(),
            "open_maintenance": open_maintenance,
        },
        "by_status": {s: by_status.get(s, 0) for s in Asset.Status.values},
        "by_category": [
            {"name": r["category__name"], "color": r["category__color"], "count": r["count"], "value": str(r["value"] or 0)}
            for r in by_category
        ],
        "by_department": [{"name": r["department__name"], "count": r["count"]} for r in by_department],
        "timeline": timeline,
        "warranty": warranty_buckets,
        "expiring_soon": expiring_soon,
        "maintenance_due": maintenance_due,
        "recent_activity": recent,
    }


def personal_stats(user) -> dict:
    mine = Asset.objects.filter(assigned_to=user).exclude(status=Asset.Status.RETIRED)
    return {
        "my_assets": mine.count(),
        "my_value": str(mine.aggregate(v=Sum("purchase_cost"))["v"] or 0),
        "awaiting_signature": Handover.objects.filter(status=Handover.Status.PENDING, signer=user).count(),
        "my_by_status": dict(mine.values_list("status").annotate(c=Count("id")).values_list("status", "c")),
        "my_warranty_expiring": mine.filter(
            Q(warranty_expiry__gte=timezone.localdate())
            & Q(warranty_expiry__lte=timezone.localdate() + datetime.timedelta(days=30))
        ).count(),
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
def stats(request):
    payload = {"personal": personal_stats(request.user)}
    if is_manager(request.user):
        data = cache.get(CACHE_KEY)
        if data is None:
            data = compute_stats()
            cache.set(CACHE_KEY, data, CACHE_TTL)
        payload.update(data)
    return Response(payload)
