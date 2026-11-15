import datetime

import pytest

from apps.assets.models import Asset, AssetEvent, Category
from apps.audit.models import AuditLog

from .conftest import AssetFactory, CategoryFactory

pytestmark = pytest.mark.django_db


def payload(category, **extra):
    data = {
        "name": "MacBook Pro",
        "category": category.id,
        "serial_number": "C02XYZ",
        "custom_data": {"ram_gb": "32", "os": "macOS"},
    }
    data.update(extra)
    return data


def test_manager_creates_asset_with_generated_tag_history_and_audit(manager_client, category, manager):
    res = manager_client.post("/api/assets/", payload(category), format="json")
    assert res.status_code == 201, res.data
    assert res.data["asset_tag"].startswith("AST-")
    assert res.data["custom_data"] == {"ram_gb": 32, "os": "macOS"}
    asset = Asset.objects.get(pk=res.data["id"])
    assert asset.created_by == manager and asset.status == "in_stock"
    assert asset.events.filter(event_type=AssetEvent.Type.CREATED).exists()
    assert AuditLog.objects.filter(action="create", model="assets.asset", object_id=str(asset.pk)).exists()


def test_asset_tags_are_sequential(manager_client, category):
    a = manager_client.post("/api/assets/", payload(category, serial_number="A1"), format="json").data["asset_tag"]
    b = manager_client.post("/api/assets/", payload(category, serial_number="A2"), format="json").data["asset_tag"]
    assert int(b.split("-")[1]) == int(a.split("-")[1]) + 1


def test_custom_field_validation(manager_client, category):
    res = manager_client.post("/api/assets/", payload(category, custom_data={"os": "Linux"}), format="json")
    assert res.status_code == 400
    assert set(res.data["custom_data"]) == {"ram_gb", "os"}


def test_inherited_custom_fields_apply_to_children(manager_client, category):
    child = CategoryFactory(name="Gaming laptops", parent=category)
    res = manager_client.post("/api/assets/", payload(child, custom_data={}), format="json")
    assert res.status_code == 400 and "ram_gb" in res.data["custom_data"]


def test_duplicate_serial_rejected_and_blank_serial_allowed_twice(manager_client, category):
    assert manager_client.post("/api/assets/", payload(category), format="json").status_code == 201
    assert manager_client.post("/api/assets/", payload(category), format="json").status_code == 400
    assert manager_client.post("/api/assets/", payload(category, serial_number=""), format="json").status_code == 201
    assert manager_client.post("/api/assets/", payload(category, serial_number=""), format="json").status_code == 201


def test_warranty_before_purchase_rejected(manager_client, category):
    res = manager_client.post(
        "/api/assets/", payload(category, purchase_date="2025-01-10", warranty_expiry="2024-01-01"), format="json"
    )
    assert res.status_code == 400 and "warranty_expiry" in res.data


def test_status_cannot_be_changed_via_update(manager_client, asset):
    res = manager_client.patch(f"/api/assets/{asset.id}/", {"status": "assigned", "name": "Renamed"}, format="json")
    assert res.status_code == 200
    asset.refresh_from_db()
    assert asset.status == "in_stock" and asset.name == "Renamed"
    assert asset.events.filter(event_type="updated").exists()


def test_employee_is_read_only_and_sees_only_own_assets(employee_client, employee, category):
    mine = AssetFactory(category=category, assigned_to=employee, status="assigned", custom_data={"ram_gb": 8})
    AssetFactory(category=category, custom_data={"ram_gb": 8})
    res = employee_client.get("/api/assets/")
    assert res.status_code == 200
    assert [a["id"] for a in res.data["results"]] == [mine.id]
    assert employee_client.post("/api/assets/", payload(category), format="json").status_code == 403
    assert employee_client.get("/api/my-assets/").data["count"] == 1


def test_filters_and_search(manager_client, category):
    soon = datetime.date.today() + datetime.timedelta(days=10)
    a = AssetFactory(category=category, name="Expiring Dell", warranty_expiry=soon, custom_data={"ram_gb": 8})
    AssetFactory(category=category, name="Old HP", status="retired", custom_data={"ram_gb": 8})
    res = manager_client.get("/api/assets/", {"warranty_expiring_in": 30})
    assert [r["id"] for r in res.data["results"]] == [a.id]
    assert manager_client.get("/api/assets/", {"status": "retired"}).data["count"] == 1
    assert manager_client.get("/api/assets/", {"status": "retired,in_stock"}).data["count"] == 2
    assert manager_client.get("/api/assets/", {"search": "dell"}).data["count"] == 1
    child = Category.objects.create(name="Sub", parent=category)
    AssetFactory(category=child, custom_data={"ram_gb": 8})
    assert manager_client.get("/api/assets/", {"category": category.id}).data["count"] == 3


@pytest.mark.parametrize(
    "start,holder,target,ok",
    [
        ("in_stock", False, "in_repair", True),
        ("in_stock", False, "retired", True),
        ("in_stock", False, "assigned", False),
        ("assigned", True, "retired", False),
        ("assigned", True, "in_stock", False),
        ("assigned", True, "lost", True),
        ("in_repair", True, "assigned", True),
        ("retired", False, "in_stock", True),
        ("retired", False, "in_repair", False),
    ],
)
def test_status_machine(manager_client, category, employee, start, holder, target, ok):
    asset = AssetFactory(category=category, status=start, assigned_to=employee if holder else None, custom_data={"ram_gb": 8})
    res = manager_client.post(f"/api/assets/{asset.id}/change-status/", {"status": target, "notes": "x"}, format="json")
    assert (res.status_code == 200) is ok, res.data
    asset.refresh_from_db()
    assert (asset.status == target) is ok
    if ok:
        assert asset.events.filter(event_type="status_changed", to_status=target).exists()


def test_qr_barcode_and_lookup(manager_client, asset):
    res = manager_client.get(f"/api/assets/{asset.id}/qr/")
    assert res.status_code == 200 and res["Content-Type"] == "image/png"
    assert manager_client.get(f"/api/assets/{asset.id}/qr/", {"fmt": "svg"})["Content-Type"] == "image/svg+xml"
    assert manager_client.get(f"/api/assets/{asset.id}/barcode/")["Content-Type"] == "image/svg+xml"
    assert manager_client.get("/api/assets/lookup/", {"code": asset.asset_tag.lower()}).data["id"] == asset.id
    assert manager_client.get("/api/assets/lookup/", {"code": f"https://x.io/a/{asset.asset_tag}"}).data["id"] == asset.id
    assert manager_client.get("/api/assets/lookup/", {"code": asset.serial_number}).data["id"] == asset.id
    assert manager_client.get("/api/assets/lookup/", {"code": "nope"}).status_code == 404


def test_photo_upload_primary_and_delete(manager_client, asset, png_file):
    res = manager_client.post(f"/api/assets/{asset.id}/photos/", {"image": png_file, "caption": "front"}, format="multipart")
    assert res.status_code == 201, res.data
    assert res.data["is_primary"] is True
    detail = manager_client.get(f"/api/assets/{asset.id}/").data
    assert detail["thumbnail"] and len(detail["photos"]) == 1
    assert manager_client.delete(f"/api/assets/{asset.id}/photos/{res.data['id']}/").status_code == 204


def test_photo_rejects_non_image(manager_client, asset):
    from django.core.files.uploadedfile import SimpleUploadedFile

    bad = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
    assert manager_client.post(f"/api/assets/{asset.id}/photos/", {"image": bad}, format="multipart").status_code == 400


def test_bulk_update_and_labels(manager_client, category, location):
    a, b = AssetFactory(category=category, custom_data={"ram_gb": 1}), AssetFactory(category=category, custom_data={"ram_gb": 1})
    res = manager_client.post("/api/assets/bulk-update/", {"ids": [a.id, b.id], "location": location.id}, format="json")
    assert res.data == {"updated": 2}
    assert Asset.objects.filter(location=location).count() == 2
    pdf = manager_client.post("/api/assets/labels/", {"ids": [a.id, b.id]}, format="json")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_delete_assigned_asset_blocked(manager_client, category, employee):
    asset = AssetFactory(category=category, status="assigned", assigned_to=employee, custom_data={"ram_gb": 1})
    assert manager_client.delete(f"/api/assets/{asset.id}/").status_code == 400


def test_history_endpoint(manager_client, category):
    asset_id = manager_client.post("/api/assets/", payload(category), format="json").data["id"]
    res = manager_client.get(f"/api/assets/{asset_id}/history/")
    assert res.status_code == 200 and res.data["results"][0]["event_type"] == "created"


def test_category_crud_with_custom_fields(manager_client, employee_client):
    data = {
        "name": "Vehicles",
        "custom_fields": [
            {"key": "plate", "label": "Plate", "field_type": "text", "required": True},
            {"key": "fuel", "label": "Fuel", "field_type": "select", "options": ["Petrol", "EV"]},
        ],
    }
    res = manager_client.post("/api/categories/", data, format="json")
    assert res.status_code == 201, res.data
    cid = res.data["id"]
    assert res.data["slug"] == "vehicles"
    res = manager_client.patch(
        f"/api/categories/{cid}/", {"custom_fields": [{"key": "plate", "label": "Plate #", "field_type": "text"}]}, format="json"
    )
    assert [f["label"] for f in res.data["custom_fields"]] == ["Plate #"]
    bad = manager_client.post(
        "/api/categories/", {"name": "X", "custom_fields": [{"key": "a", "label": "A", "field_type": "select"}]}, format="json"
    )
    assert bad.status_code == 400
    assert employee_client.get("/api/categories/").status_code == 200
    assert employee_client.post("/api/categories/", {"name": "Nope"}, format="json").status_code == 403


def test_category_cycle_prevented(manager_client):
    parent = CategoryFactory()
    child = CategoryFactory(parent=parent)
    res = manager_client.patch(f"/api/categories/{parent.id}/", {"parent": child.id}, format="json")
    assert res.status_code == 400


def test_category_in_use_cannot_be_deleted(manager_client, asset):
    assert manager_client.delete(f"/api/categories/{asset.category_id}/").status_code == 409
