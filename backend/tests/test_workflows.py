import pytest

from apps.assets.models import Asset, AssetEvent
from apps.notifications.models import Notification
from apps.workflows.models import Handover

from .conftest import AssetFactory, UserFactory

pytestmark = pytest.mark.django_db


def make_asset(category, **kw):
    kw.setdefault("custom_data", {"ram_gb": 8})
    return AssetFactory(category=category, **kw)


# --- Receiving -----------------------------------------------------------------
def test_receipt_creates_assets_with_purchase_info(manager_client, category, location, signature):
    from .conftest import VendorFactory

    vendor = VendorFactory()
    res = manager_client.post(
        "/api/receipts/",
        {
            "vendor": vendor.id,
            "invoice_number": "INV-9",
            "location": location.id,
            "signature": signature,
            "signed_name": "Store Keeper",
            "items": [
                {
                    "name": "ThinkPad",
                    "category": category.id,
                    "quantity": 3,
                    "serial_numbers": ["S1", "S2"],
                    "unit_cost": "1200.00",
                    "custom_data": {"ram_gb": 16},
                    "maintenance_interval_days": 90,
                },
            ],
        },
        format="json",
    )
    assert res.status_code == 201, res.data
    assert res.data["reference"].startswith("GRN-")
    assert res.data["asset_count"] == 3 and res.data["is_signed"] is True
    assets = Asset.objects.filter(receipt_id=res.data["id"]).order_by("asset_tag")
    assert [a.serial_number for a in assets] == ["S1", "S2", None]
    assert all(a.vendor == vendor and a.location == location and a.invoice_number == "INV-9" for a in assets)
    assert all(a.next_maintenance_date for a in assets)
    assert AssetEvent.objects.filter(event_type="received", receipt_id=res.data["id"]).count() == 3
    pdf = manager_client.get(f"/api/receipts/{res.data['id']}/pdf/")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_receipt_rejects_existing_serial(manager_client, category):
    make_asset(category, serial_number="DUP")
    res = manager_client.post(
        "/api/receipts/",
        {"items": [{"name": "X", "category": category.id, "serial_numbers": ["DUP"], "custom_data": {"ram_gb": 1}}]},
        format="json",
    )
    assert res.status_code == 400


def test_receipt_validates_custom_fields_atomically(manager_client, category):
    res = manager_client.post("/api/receipts/", {"items": [{"name": "X", "category": category.id, "quantity": 2}]}, format="json")
    assert res.status_code == 400
    assert Asset.objects.count() == 0


def test_employee_cannot_receive(employee_client, category):
    assert employee_client.post("/api/receipts/", {"items": []}, format="json").status_code == 403


# --- Handovers -----------------------------------------------------------------
def issue(client, assets, to_user, **extra):
    data = {"type": "issue", "to_user": to_user.id, "items": [{"asset": a.id, "condition": "good"} for a in assets]}
    data.update(extra)
    return client.post("/api/handovers/", data, format="json")


def test_issue_pending_then_employee_signs(manager_client, client_for, employee, category, signature):
    a1, a2 = make_asset(category), make_asset(category)
    res = issue(manager_client, [a1, a2], employee, notes="Onboarding")
    assert res.status_code == 201, res.data
    hid = res.data["id"]
    assert res.data["status"] == "pending" and res.data["signer"] == employee.id
    a1.refresh_from_db()
    assert a1.status == "in_stock"  # nothing applied before sign-off
    assert Notification.objects.filter(recipient=employee, category="handover").exists()

    emp_client = client_for(employee)
    assert emp_client.get(f"/api/handovers/{hid}/").data["can_sign"] is True
    signed = emp_client.post(f"/api/handovers/{hid}/sign/", {"signature": signature, "signed_name": "Eve"}, format="json")
    assert signed.status_code == 200, signed.data
    assert signed.data["status"] == "completed" and signed.data["is_signed"] is True
    for a in (a1, a2):
        a.refresh_from_db()
        assert a.status == "assigned" and a.assigned_to == employee and a.department == employee.department
        assert a.events.filter(event_type="issued", handover_id=hid).exists()
    pdf = manager_client.get(f"/api/handovers/{hid}/pdf/")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_issue_with_in_person_signature_completes_immediately(manager_client, employee, category, signature):
    a = make_asset(category)
    res = issue(manager_client, [a], employee, signature=signature, signed_name="Eve", issuer_signature=signature)
    assert res.status_code == 201, res.data
    assert res.data["status"] == "completed" and res.data["has_issuer_signature"]
    a.refresh_from_db()
    assert a.status == "assigned"


def test_cannot_issue_assigned_or_pending_assets(manager_client, employee, other_employee, category):
    held = make_asset(category, status="assigned", assigned_to=other_employee)
    assert issue(manager_client, [held], employee).status_code == 400
    a = make_asset(category)
    assert issue(manager_client, [a], employee).status_code == 201
    res = issue(manager_client, [a], other_employee)
    assert res.status_code == 400 and "pending" in str(res.data)


def test_other_employee_cannot_sign_or_view(manager_client, client_for, employee, other_employee, category, signature):
    hid = issue(manager_client, [make_asset(category)], employee).data["id"]
    other = client_for(other_employee)
    assert other.get(f"/api/handovers/{hid}/").status_code == 404
    assert other.post(f"/api/handovers/{hid}/sign/", {"signature": signature}, format="json").status_code == 404


def test_blank_signature_rejected(manager_client, client_for, employee, category):
    import base64
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (300, 100), (0, 0, 0, 0)).save(buf, format="PNG")
    blank = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    hid = issue(manager_client, [make_asset(category)], employee).data["id"]
    res = client_for(employee).post(f"/api/handovers/{hid}/sign/", {"signature": blank}, format="json")
    assert res.status_code == 400


def test_transfer_between_employees(manager_client, employee, other_employee, category, signature, location):
    a = make_asset(category, status="assigned", assigned_to=employee, department=employee.department)
    res = manager_client.post(
        "/api/handovers/",
        {
            "type": "transfer",
            "to_user": other_employee.id,
            "to_location": location.id,
            "items": [{"asset": a.id}],
            "signature": signature,
        },
        format="json",
    )
    assert res.status_code == 201, res.data
    assert res.data["from_user"] == employee.id
    a.refresh_from_db()
    assert a.assigned_to == other_employee and a.location == location
    ev = a.events.get(event_type="transferred")
    assert ev.from_user == employee and ev.to_user == other_employee


def test_transfer_requires_single_holder(manager_client, employee, other_employee, category):
    a = make_asset(category, status="assigned", assigned_to=employee)
    b = make_asset(category, status="assigned", assigned_to=other_employee)
    third = UserFactory()
    res = manager_client.post(
        "/api/handovers/", {"type": "transfer", "to_user": third.id, "items": [{"asset": a.id}, {"asset": b.id}]}, format="json"
    )
    assert res.status_code == 400


def test_return_flow_signed_by_returning_employee(manager_client, client_for, employee, category, signature):
    a = make_asset(category, status="assigned", assigned_to=employee, department=employee.department)
    res = manager_client.post(
        "/api/handovers/", {"type": "return", "items": [{"asset": a.id, "condition": "fair"}]}, format="json"
    )
    assert res.status_code == 201, res.data
    assert res.data["signer"] == employee.id
    done = client_for(employee).post(f"/api/handovers/{res.data['id']}/sign/", {"signature": signature}, format="json")
    assert done.status_code == 200
    a.refresh_from_db()
    assert a.status == "in_stock" and a.assigned_to is None and a.department is None and a.condition == "fair"


def test_cancel_and_cannot_sign_cancelled(manager_client, employee, category, signature):
    hid = issue(manager_client, [make_asset(category)], employee).data["id"]
    res = manager_client.post(f"/api/handovers/{hid}/cancel/", {"reason": "typo"}, format="json")
    assert res.data["status"] == "cancelled"
    assert manager_client.post(f"/api/handovers/{hid}/sign/", {"signature": signature}, format="json").status_code == 400
    assert manager_client.post(f"/api/handovers/{hid}/cancel/", {}, format="json").status_code == 400


def test_sign_revalidates_asset_state(manager_client, employee, category, signature):
    a = make_asset(category)
    hid = issue(manager_client, [a], employee).data["id"]
    Asset.objects.filter(pk=a.pk).update(status="lost")
    res = manager_client.post(f"/api/handovers/{hid}/sign/", {"signature": signature}, format="json")
    assert res.status_code == 400
    assert Handover.objects.get(pk=hid).status == "pending"


def test_employee_handover_list_and_awaiting_filter(manager_client, client_for, employee, other_employee, category):
    issue(manager_client, [make_asset(category)], employee)
    issue(manager_client, [make_asset(category)], other_employee)
    emp = client_for(employee)
    assert emp.get("/api/handovers/").data["count"] == 1
    assert emp.get("/api/handovers/", {"awaiting_me": "1"}).data["count"] == 1
    assert emp.post("/api/handovers/", {"type": "issue", "items": []}, format="json").status_code == 403
