from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.assets.models import Asset, AssetEvent
from apps.assets.services import clean_custom_data, log_event
from apps.audit.models import AuditLog
from apps.audit.services import record
from apps.core.exceptions import DomainError
from apps.core.permissions import is_manager
from apps.notifications.models import Notification
from apps.notifications.services import notify, notify_managers

from .models import GoodsReceipt, Handover, HandoverItem

S = Asset.Status
T = Handover.Type


# --- Receiving -----------------------------------------------------------------
@transaction.atomic
def create_receipt(data: dict, actor, signature_file=None) -> GoodsReceipt:
    items = data.pop("items")
    receipt = GoodsReceipt.objects.create(received_by=actor, **data)
    if signature_file is not None:
        receipt.signature.save(signature_file.name, signature_file, save=False)
        receipt.signed_at = timezone.now()
        receipt.signed_name = receipt.signed_name or (actor.get_full_name() if actor else "")
        receipt.save(update_fields=["signature", "signed_at", "signed_name"])
    created = 0
    for item in items:
        serials = item.pop("serial_numbers", []) or []
        quantity = item.pop("quantity", 1)
        custom = clean_custom_data(item["category"], item.pop("custom_data", {}))
        unit_cost = item.pop("unit_cost", None)
        interval = item.get("maintenance_interval_days")
        if interval and not item.get("next_maintenance_date"):
            item["next_maintenance_date"] = receipt.received_date + timedelta(days=interval)
        for i in range(quantity):
            asset = Asset.objects.create(
                **item,
                serial_number=serials[i] if i < len(serials) else None,
                custom_data=custom,
                purchase_cost=unit_cost,
                purchase_date=receipt.received_date,
                vendor=receipt.vendor,
                invoice_number=receipt.invoice_number,
                po_number=receipt.po_number,
                location=receipt.location,
                receipt=receipt,
                status=S.IN_STOCK,
                created_by=actor,
            )
            log_event(asset, AssetEvent.Type.RECEIVED, actor, to_status=S.IN_STOCK, to_location=receipt.location, receipt=receipt)
            created += 1
    record(AuditLog.Action.CREATE, actor, receipt, {"assets_created": created})
    notify_managers(
        title=f"Goods received: {receipt.reference}",
        message=f"{created} asset(s) received{f' from {receipt.vendor}' if receipt.vendor else ''}.",
        category=Notification.Category.RECEIVING,
        level=Notification.Level.SUCCESS,
        link=f"/receiving/{receipt.pk}",
        exclude=[actor] if actor else None,
    )
    return receipt


# --- Handovers -----------------------------------------------------------------
def _holder(asset):
    return (asset.assigned_to_id, asset.department_id)


def _active_handover_conflicts(asset_ids, exclude_pk=None):
    qs = HandoverItem.objects.filter(asset_id__in=asset_ids, handover__status=Handover.Status.PENDING)
    if exclude_pk:
        qs = qs.exclude(handover_id=exclude_pk)
    return set(qs.values_list("asset__asset_tag", flat=True))


def validate_assets_for(kind: str, assets: list[Asset]):
    """Raise DomainError if any asset can't take part in a handover of `kind`."""
    if not assets:
        raise DomainError("Select at least one asset.", field="items")
    errors = []
    for a in assets:
        if kind == T.ISSUE and a.status != S.IN_STOCK:
            errors.append(f"{a.asset_tag} is {a.get_status_display().lower()}, not in stock")
        elif kind == T.TRANSFER and a.status != S.ASSIGNED:
            errors.append(f"{a.asset_tag} is not currently assigned")
        elif kind == T.RETURN and (a.status not in (S.ASSIGNED, S.IN_REPAIR) or not a.has_holder):
            errors.append(f"{a.asset_tag} is not held by anyone")
    if errors:
        raise DomainError("; ".join(errors) + ".", field="items")
    if kind in (T.TRANSFER, T.RETURN) and len({_holder(a) for a in assets}) > 1:
        raise DomainError("All assets must be held by the same person/department.", field="items")


@transaction.atomic
def create_handover(data: dict, actor, issuer_signature=None, signature=None, signed_name="", ip=None) -> Handover:
    items = data.pop("items")
    kind = data["type"]
    ids = [i["asset"].pk for i in items]
    assets = list(Asset.objects.select_for_update(of=("self",)).filter(pk__in=ids).select_related("assigned_to", "department"))
    validate_assets_for(kind, assets)
    conflicts = _active_handover_conflicts(ids)
    if conflicts:
        raise DomainError(f"Already in a pending handover: {', '.join(sorted(conflicts))}.", field="items")

    to_user, to_department = data.get("to_user"), data.get("to_department")
    if kind in (T.ISSUE, T.TRANSFER):
        if not to_user and not to_department:
            raise DomainError("Choose an employee or a department to receive the assets.", field="to_user")
        if to_user and not to_user.is_active:
            raise DomainError("The recipient account is inactive.", field="to_user")
        if to_user and not to_department:
            data["to_department"] = to_user.department
    if kind in (T.TRANSFER, T.RETURN):
        first = assets[0]
        data["from_user"], data["from_department"] = first.assigned_to, first.department
    if kind == T.TRANSFER and (data.get("from_user"), data.get("from_department")) == (to_user, data.get("to_department")):
        raise DomainError("Assets are already held by this recipient.", field="to_user")
    if kind == T.RETURN:
        data["to_user"] = None
        data["to_department"] = None

    signer = data.get("to_user") if kind in (T.ISSUE, T.TRANSFER) else data.get("from_user")
    handover = Handover.objects.create(created_by=actor, signer=signer, **data)
    by_id = {a.pk: a for a in assets}
    HandoverItem.objects.bulk_create(
        [
            HandoverItem(
                handover=handover,
                asset=by_id[i["asset"].pk],
                condition=i.get("condition") or by_id[i["asset"].pk].condition,
                notes=i.get("notes", ""),
            )
            for i in items
        ]
    )
    if issuer_signature is not None:
        handover.issuer_signature.save(issuer_signature.name, issuer_signature, save=True)
    record(AuditLog.Action.CREATE, actor, handover, {"type": kind, "assets": [a.asset_tag for a in assets]})

    if signature is not None:
        return complete_handover(handover, signature, signed_name, actor, ip)

    if signer and signer != actor:
        notify(
            [signer],
            title=f"Please sign handover {handover.reference}",
            message=f"{len(assets)} asset(s) — {handover.get_type_display().lower()} awaiting your signature.",
            category=Notification.Category.HANDOVER,
            level=Notification.Level.WARNING,
            link=f"/handovers/{handover.pk}",
            data={"handover": handover.pk, "action": "sign"},
        )
    return handover


def can_sign(handover: Handover, user) -> bool:
    if handover.status != Handover.Status.PENDING:
        return False
    return is_manager(user) or (handover.signer_id is not None and handover.signer_id == user.pk)


@transaction.atomic
def complete_handover(handover: Handover, signature_file, signed_name: str, actor, ip=None) -> Handover:
    handover = Handover.objects.select_for_update(of=("self",)).get(pk=handover.pk)
    if handover.status != Handover.Status.PENDING:
        raise DomainError(f"Handover is already {handover.get_status_display().lower()}.")
    if not can_sign(handover, actor):
        raise DomainError("You are not allowed to sign this handover.", code="forbidden")

    items = list(handover.items.select_related("asset"))
    assets = list(Asset.objects.select_for_update(of=("self",)).filter(pk__in=[i.asset_id for i in items]))
    validate_assets_for(handover.type, assets)  # state may have changed since creation
    if handover.type in (T.TRANSFER, T.RETURN):
        expected = (handover.from_user_id, handover.from_department_id)
        if any(_holder(a) != expected for a in assets):
            raise DomainError("Asset holders changed since this handover was created; cancel and recreate it.")
    by_id = {a.pk: a for a in assets}
    now = timezone.now()

    for item in items:
        asset = by_id[item.asset_id]
        before = {
            "from_status": asset.status,
            "from_user": asset.assigned_to,
            "from_department": asset.department,
            "from_location": asset.location,
        }
        if handover.type in (T.ISSUE, T.TRANSFER):
            asset.status = S.ASSIGNED
            asset.assigned_to = handover.to_user
            asset.department = handover.to_department
            asset.assigned_at = now
            event = AssetEvent.Type.ISSUED if handover.type == T.ISSUE else AssetEvent.Type.TRANSFERRED
        else:
            asset.status = S.IN_STOCK
            asset.assigned_to = None
            asset.department = None
            asset.assigned_at = None
            event = AssetEvent.Type.RETURNED
        if handover.to_location_id:
            asset.location = handover.to_location
        if item.condition in Asset.Condition.values:
            asset.condition = item.condition
        asset.save()
        log_event(
            asset,
            event,
            actor,
            to_status=asset.status,
            to_user=asset.assigned_to,
            to_department=asset.department,
            to_location=asset.location,
            handover=handover,
            notes=item.notes or handover.notes,
            **before,
        )

    handover.signature.save(signature_file.name, signature_file, save=False)
    handover.signed_name = (signed_name or actor.get_full_name() or actor.email)[:160]
    handover.signed_by = actor
    handover.signed_at = now
    handover.signed_ip = ip
    handover.status = Handover.Status.COMPLETED
    handover.completed_at = now
    handover.save()
    record(AuditLog.Action.SIGN, actor, handover, {"signed_name": handover.signed_name, "assets": len(items)})

    recipients = {u for u in (handover.to_user, handover.from_user, handover.created_by) if u and u != actor}
    if recipients:
        notify(
            list(recipients),
            title=f"Handover {handover.reference} completed",
            message=f"{handover.get_type_display()} of {len(items)} asset(s) was signed by {handover.signed_name}.",
            category=Notification.Category.HANDOVER,
            level=Notification.Level.SUCCESS,
            link=f"/handovers/{handover.pk}",
            data={"handover": handover.pk},
        )
    return handover


@transaction.atomic
def cancel_handover(handover: Handover, actor, reason: str = "") -> Handover:
    handover = Handover.objects.select_for_update(of=("self",)).get(pk=handover.pk)
    if handover.status != Handover.Status.PENDING:
        raise DomainError("Only pending handovers can be cancelled.")
    handover.status = Handover.Status.CANCELLED
    handover.cancelled_at = timezone.now()
    handover.cancel_reason = reason[:500]
    handover.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])
    record(AuditLog.Action.CANCEL, actor, handover, {"reason": reason})
    if handover.signer and handover.signer != actor:
        notify(
            [handover.signer],
            title=f"Handover {handover.reference} cancelled",
            message=reason or "The pending handover was cancelled.",
            category=Notification.Category.HANDOVER,
            level=Notification.Level.INFO,
            link=f"/handovers/{handover.pk}",
        )
    return handover
