import csv
import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import load_workbook

from apps.assets.models import Asset
from apps.audit.models import AuditLog
from apps.maintenance.models import MaintenanceRecord
from apps.notifications.models import Notification
from apps.notifications.tasks import check_maintenance_due, check_overdue_returns, check_warranty_expiry
from apps.workflows.models import Handover, HandoverItem

from .conftest import AssetFactory

pytestmark = pytest.mark.django_db


def csv_upload(rows, name="assets.csv"):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return SimpleUploadedFile(name, buf.getvalue().encode(), content_type="text/csv")


# --- Import / export ---------------------------------------------------------
def test_export_csv_and_xlsx(manager_client, asset):
    res = manager_client.get("/api/assets/export/", {"file_format": "csv"})
    assert res.status_code == 200 and res["Content-Type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
    assert rows[0][0] == "asset_tag" and rows[1][0] == asset.asset_tag
    assert "cf:ram_gb" in rows[0]
    res = manager_client.get("/api/assets/export/")
    wb = load_workbook(io.BytesIO(res.content))
    assert wb.active["A2"].value == asset.asset_tag
    assert AuditLog.objects.filter(action="export").count() == 2


def test_export_neutralises_formula_injection(manager_client, category):
    AssetFactory(category=category, name='=HYPERLINK("http://evil")', custom_data={"ram_gb": 1})
    content = manager_client.get("/api/assets/export/", {"file_format": "csv"}).content.decode("utf-8-sig")
    assert "'=HYPERLINK" in content


def test_import_dry_run_then_commit(manager_client, category, location):
    rows = [
        {
            "asset_tag": "",
            "name": "Imported A",
            "category": "Laptops",
            "location": "hq",
            "serial_number": "IMP-1",
            "cf:ram_gb": "16",
        },
        {
            "asset_tag": "",
            "name": "Imported B",
            "category": "laptops",
            "location": "",
            "serial_number": "IMP-2",
            "cf:ram_gb": "8",
        },
    ]
    res = manager_client.post("/api/assets/import/", {"file": csv_upload(rows), "dry_run": "true"}, format="multipart")
    assert res.status_code == 200, res.data
    assert res.data["created"] == 2 and Asset.objects.count() == 0
    res = manager_client.post("/api/assets/import/", {"file": csv_upload(rows)}, format="multipart")
    assert res.status_code == 200 and res.data["created"] == 2
    a = Asset.objects.get(serial_number="IMP-1")
    assert a.location == location and a.custom_data == {"ram_gb": 16}
    assert AuditLog.objects.filter(action="import").exists()


def test_import_is_all_or_nothing(manager_client, category):
    rows = [
        {"name": "Good", "category": "Laptops", "cf:ram_gb": "16", "purchase_date": "2025-01-01"},
        {"name": "Bad", "category": "Unknown", "cf:ram_gb": "x", "purchase_date": "01/02/2025"},
    ]
    res = manager_client.post("/api/assets/import/", {"file": csv_upload(rows)}, format="multipart")
    assert res.status_code == 400
    assert res.data["errors"][0]["row"] == 3
    assert {"category", "purchase_date"} <= set(res.data["errors"][0]["errors"])
    assert Asset.objects.count() == 0


def test_import_updates_by_tag(manager_client, asset):
    rows = [{"asset_tag": asset.asset_tag, "name": "Renamed", "category": "", "condition": "fair", "cf:ram_gb": "64"}]
    res = manager_client.post("/api/assets/import/", {"file": csv_upload(rows)}, format="multipart")
    assert res.status_code == 200, res.data
    asset.refresh_from_db()
    assert asset.name == "Renamed" and asset.condition == "fair" and asset.custom_data["ram_gb"] == 64


def test_import_rejects_bad_file_type(manager_client):
    upload = SimpleUploadedFile("x.txt", b"hello", content_type="text/plain")
    assert manager_client.post("/api/assets/import/", {"file": upload}, format="multipart").status_code == 400


def test_import_template(manager_client):
    res = manager_client.get("/api/assets/import-template/")
    assert res.status_code == 200
    assert load_workbook(io.BytesIO(res.content)).active["B1"].value == "name"


# --- Maintenance -------------------------------------------------------------
def test_maintenance_start_and_complete_restores_status(manager_client, category, employee):
    asset = AssetFactory(
        category=category, status="assigned", assigned_to=employee, maintenance_interval_days=30, custom_data={"ram_gb": 1}
    )
    res = manager_client.post(
        "/api/maintenance/",
        {"asset": asset.id, "title": "Battery swap", "kind": "corrective", "scheduled_date": "2026-01-01"},
        format="json",
    )
    assert res.status_code == 201, res.data
    mid = res.data["id"]
    manager_client.post(f"/api/maintenance/{mid}/start/")
    asset.refresh_from_db()
    assert asset.status == "in_repair"
    res = manager_client.post(f"/api/maintenance/{mid}/complete/", {"cost": "120.50", "condition": "good"}, format="json")
    assert res.status_code == 200 and res.data["status"] == "completed"
    asset.refresh_from_db()
    assert asset.status == "assigned"
    assert asset.next_maintenance_date == datetime.date.today() + datetime.timedelta(days=30)
    assert asset.events.filter(event_type="maintenance_completed").exists()


def test_maintenance_cannot_start_twice(manager_client, asset):
    rec = MaintenanceRecord.objects.create(asset=asset, title="A", scheduled_date=datetime.date.today())
    assert manager_client.post(f"/api/maintenance/{rec.id}/start/").status_code == 200
    assert manager_client.post(f"/api/maintenance/{rec.id}/start/").status_code == 400
    assert manager_client.post(f"/api/maintenance/{rec.id}/cancel/").status_code == 200
    asset.refresh_from_db()
    assert asset.status == "in_stock"


def test_employee_cannot_access_maintenance(employee_client):
    assert employee_client.get("/api/maintenance/").status_code == 403


# --- Alerts ------------------------------------------------------------------
def test_warranty_alerts_thresholds_and_dedupe(manager, employee, category):
    today = datetime.date.today()
    AssetFactory(
        category=category,
        warranty_expiry=today + datetime.timedelta(days=5),
        assigned_to=employee,
        status="assigned",
        custom_data={"ram_gb": 1},
    )
    AssetFactory(category=category, warranty_expiry=today + datetime.timedelta(days=200), custom_data={"ram_gb": 1})
    AssetFactory(
        category=category, warranty_expiry=today + datetime.timedelta(days=3), status="retired", custom_data={"ram_gb": 1}
    )
    assert check_warranty_expiry() == 2  # manager + holder
    assert check_warranty_expiry() == 0  # deduped
    n = Notification.objects.get(recipient=employee)
    assert n.category == "warranty" and n.level == "critical"


def test_maintenance_due_alerts(manager, category):
    AssetFactory(
        category=category, next_maintenance_date=datetime.date.today() - datetime.timedelta(days=1), custom_data={"ram_gb": 1}
    )
    assert check_maintenance_due() == 1
    assert Notification.objects.get(recipient=manager).title.startswith("Maintenance overdue")


def test_overdue_return_alert(manager, employee, category):
    a = AssetFactory(category=category, status="assigned", assigned_to=employee, custom_data={"ram_gb": 1})
    h = Handover.objects.create(
        type="issue",
        status="completed",
        to_user=employee,
        expected_return_date=datetime.date.today() - datetime.timedelta(days=2),
    )
    HandoverItem.objects.create(handover=h, asset=a)
    assert check_overdue_returns() == 2
    assert check_overdue_returns() == 0


def test_notifications_api(employee_client, employee):
    from apps.notifications.services import notify

    notify([employee], title="Hello")
    notify([employee], title="World")
    assert employee_client.get("/api/notifications/unread-count/").data == {"unread": 2}
    nid = employee_client.get("/api/notifications/").data["results"][0]["id"]
    assert employee_client.post(f"/api/notifications/{nid}/read/").data["is_read"] is True
    assert employee_client.post("/api/notifications/read-all/").data == {"updated": 1}
    assert employee_client.post("/api/notifications/clear-read/").data == {"deleted": 2}


def test_dashboard_stats_roles_and_cache_invalidation(
    manager_client, employee_client, category, django_capture_on_commit_callbacks
):
    AssetFactory(category=category, purchase_cost="100.00", custom_data={"ram_gb": 1})
    res = manager_client.get("/api/dashboard/stats/")
    assert res.status_code == 200
    assert res.data["totals"]["assets"] == 1 and len(res.data["timeline"]) == 12
    with django_capture_on_commit_callbacks(execute=True):
        AssetFactory(category=category, custom_data={"ram_gb": 1})
    assert manager_client.get("/api/dashboard/stats/").data["totals"]["assets"] == 2  # signal busted the cache
    emp = employee_client.get("/api/dashboard/stats/").data
    assert "totals" not in emp and emp["personal"]["my_assets"] == 0
