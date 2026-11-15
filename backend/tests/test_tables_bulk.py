import csv
import datetime
import io

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.assets.models import Asset, Location, Vendor
from apps.audit.models import AuditLog
from apps.maintenance.models import MaintenanceRecord
from apps.navigation.models import SidebarItem, TableColumn, TableDefinition, TableRecord
from apps.workflows.models import Handover, HandoverItem

from .conftest import AssetFactory, DepartmentFactory, LocationFactory, UserFactory, VendorFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("seeded_config")]


def csv_rows(res):
    assert res.content.startswith("﻿".encode())  # BOM so Excel detects UTF-8
    return list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))


# --- Table definitions --------------------------------------------------------------------
def test_every_table_page_owns_a_definition(employee_client):
    assets = TableDefinition.objects.get(source="assets")
    assert (assets.name, assets.singular) == ("Assets", "Asset")
    node = next(
        c for g in employee_client.get("/api/sidebar/").data["items"] for c in g.get("children", []) if c.get("table") == "assets"
    )
    assert node["table_meta"]["singular"] == "Asset"


def test_rename_table_updates_sidebar_and_list_meta(admin_client, manager_client, employee_client):
    d = TableDefinition.objects.get(source="assets")
    assert manager_client.patch(f"/api/table-definitions/{d.id}/", {"name": "Equipment"}, format="json").status_code == 403
    res = admin_client.patch(
        f"/api/table-definitions/{d.id}/", {"name": "Equipment", "singular": "Equipment item", "icon": "laptop"}, format="json"
    )
    assert res.status_code == 200, res.data
    item = SidebarItem.objects.get(pk=d.sidebar_item_id)
    assert (item.name, item.icon) == ("Equipment", "laptop")
    meta = manager_client.get("/api/assets/", {"with_columns": 1}).data["table"]["meta"]
    assert (meta["name"], meta["singular"]) == ("Equipment", "Equipment item")
    assert AuditLog.objects.filter(model="navigation.tabledefinition", action="update").exists()


def test_renaming_the_sidebar_page_renames_the_table(admin_client):
    d = TableDefinition.objects.get(source="vendors")
    assert admin_client.patch(f"/api/sidebar-items/{d.sidebar_item_id}/", {"name": "Suppliers"}, format="json").status_code == 200
    d.refresh_from_db()
    assert d.name == "Suppliers"


def test_table_names_are_unique_case_insensitive(admin_client):
    d = TableDefinition.objects.get(source="vendors")
    res = admin_client.patch(f"/api/table-definitions/{d.id}/", {"name": "assets"}, format="json")
    assert res.status_code == 400 and "name" in res.data
    res = admin_client.patch(f"/api/sidebar-items/{d.sidebar_item_id}/", {"name": "ASSETS"}, format="json")
    assert res.status_code == 400 and "name" in res.data


def test_create_custom_table_with_columns_and_records(admin_client, manager_client, employee_client):
    res = admin_client.post(
        "/api/table-definitions/",
        {
            "name": "Software licences",
            "singular": "Licence",
            "icon": "key-round",
            "description": "Seats and renewals",
            "visible_roles": ["admin", "manager"],
            "columns": [
                {"name": "Product", "type": "text"},
                {"name": "Seats", "type": "number"},
                {"name": "Tier", "type": "select", "options": ["Std", "Pro"]},
            ],
        },
        format="json",
    )
    assert res.status_code == 201, res.data
    d = TableDefinition.objects.get(pk=res.data["id"])
    item = d.sidebar_item
    assert item.route == "/t/software-licences" and item.table == "custom"
    keys = list(TableColumn.objects.filter(sidebar_item=item).values_list("key", flat=True))
    assert {"sno", "product", "seats", "tier"} <= set(keys)
    assert TableColumn.objects.get(sidebar_item=item, key="product").is_required

    url = f"/api/records/?table_item={item.id}"
    assert manager_client.post(url, {"custom_data": {"seats": 5}}, format="json").status_code == 400  # Product required
    assert manager_client.post(url, {"custom_data": {"product": "IDE", "tier": "Gold"}}, format="json").status_code == 400
    r = manager_client.post(url, {"custom_data": {"product": "IDE", "seats": "10", "tier": "Pro"}}, format="json")
    assert r.status_code == 201, r.data
    assert r.data["custom_data"] == {"product": "IDE", "seats": 10, "tier": "Pro"}
    rid = r.data["id"]
    assert (
        manager_client.patch(f"/api/records/{rid}/?table_item={item.id}", {"custom_data": {"seats": 12}}, format="json").data[
            "custom_data"
        ]["seats"]
        == 12
    )
    listing = manager_client.get(url + "&with_columns=1&search=IDE")
    assert listing.data["count"] == 1 and listing.data["table"]["meta"]["singular"] == "Licence"
    # Employees can't see a table hidden from their role, and can't write anywhere.
    assert employee_client.get(url).status_code == 404
    assert AuditLog.objects.filter(model="navigation.tablerecord", action="create").exists()


def test_table_with_data_cannot_be_deleted_until_archived_or_moved(admin_client, manager_client):
    a = admin_client.post("/api/table-definitions/", {"name": "Keys", "singular": "Key"}, format="json").data
    b = admin_client.post("/api/table-definitions/", {"name": "Spare keys", "singular": "Spare key"}, format="json").data
    item_a = TableDefinition.objects.get(pk=a["id"]).sidebar_item_id
    url = f"/api/records/?table_item={item_a}"
    ids = [manager_client.post(url, {"custom_data": {"name": f"K{i}"}}, format="json").data["id"] for i in range(3)]

    check = admin_client.get(f"/api/table-definitions/{a['id']}/delete-check/").data
    assert check == {"can_delete": False, "reason": check["reason"], "row_count": 3}
    assert admin_client.delete(f"/api/table-definitions/{a['id']}/").status_code == 400
    assert admin_client.delete(f"/api/sidebar-items/{item_a}/").status_code == 400  # same rule via the menu

    moved = manager_client.post(
        f"/api/records/bulk-move/?table_item={item_a}", {"ids": ids[:1], "target": b["id"]}, format="json"
    )
    assert moved.data["moved"] == 1
    assert (
        manager_client.post(f"/api/records/bulk-archive/?table_item={item_a}", {"ids": ids[1:]}, format="json").data["updated"]
        == 2
    )
    assert admin_client.delete(f"/api/table-definitions/{a['id']}/").status_code == 204
    assert not SidebarItem.objects.filter(pk=item_a).exists()
    kept = TableRecord.objects.filter(pk__in=ids[1:])
    assert kept.count() == 2 and all(r.is_archived and r.archived_from == "Keys" for r in kept)


def test_builtin_table_with_data_cannot_be_deleted(admin_client, asset):
    d = TableDefinition.objects.get(source="assets")
    res = admin_client.delete(f"/api/table-definitions/{d.id}/")
    assert res.status_code == 400 and res.data["code"] == "has_data"


def test_sidebar_reset_keeps_custom_tables(admin_client):
    d = admin_client.post("/api/table-definitions/", {"name": "Badges", "singular": "Badge"}, format="json").data
    assert admin_client.post("/api/sidebar-items/reset/").status_code == 200
    assert TableDefinition.objects.filter(pk=d["id"]).exists()
    assert TableDefinition.objects.filter(source="assets").exists()


# --- Bulk delete ----------------------------------------------------------------------------
def test_bulk_delete_assets_skips_assigned_and_history(manager_client, employee_client, category, employee):
    free = AssetFactory(category=category, custom_data={"ram_gb": 1})
    assigned = AssetFactory(category=category, status="assigned", assigned_to=employee, custom_data={"ram_gb": 1})
    with_handover = AssetFactory(category=category, custom_data={"ram_gb": 1})
    HandoverItem.objects.create(handover=Handover.objects.create(type="issue", status="cancelled"), asset=with_handover)
    with_maint = AssetFactory(category=category, custom_data={"ram_gb": 1})
    MaintenanceRecord.objects.create(asset=with_maint, title="x", scheduled_date=datetime.date.today())
    ids = [free.id, assigned.id, with_handover.id, with_maint.id]

    assert employee_client.post("/api/assets/bulk-delete/", {"ids": ids}, format="json").status_code == 403
    res = manager_client.post("/api/assets/bulk-delete/", {"ids": ids}, format="json")
    assert res.status_code == 200
    assert res.data["deleted"] == 1 and res.data["deleted_ids"] == [free.id]
    reasons = {s["id"]: s["reason"] for s in res.data["skipped"]}
    assert set(reasons) == {assigned.id, with_handover.id, with_maint.id}
    assert "Assigned" in reasons[assigned.id] and "handover" in reasons[with_handover.id]
    assert not Asset.objects.filter(pk=free.id).exists()
    assert AuditLog.objects.filter(action="delete", model="assets.asset", object_id=str(free.id)).exists()


def test_bulk_delete_all_matching_filters(manager_client, category):
    keep = AssetFactory(category=category, name="Keep me", custom_data={"ram_gb": 1})
    for i in range(3):
        AssetFactory(category=category, name=f"Old printer {i}", custom_data={"ram_gb": 1})
    res = manager_client.post("/api/assets/bulk-delete/?search=printer", {"all": True}, format="json")
    assert res.data["deleted"] == 3
    assert list(Asset.objects.values_list("id", flat=True)) == [keep.id]


def test_bulk_delete_needs_ids(manager_client):
    assert manager_client.post("/api/assets/bulk-delete/", {"ids": []}, format="json").status_code == 400
    assert manager_client.post("/api/assets/bulk-delete/", {"ids": ["x"]}, format="json").status_code == 400


def test_bulk_delete_other_tables(admin_client, manager_client, manager, category):
    # Locations/vendors in use are skipped; unused ones are deleted.
    used_loc, free_loc = LocationFactory(), LocationFactory()
    AssetFactory(category=category, location=used_loc, custom_data={"ram_gb": 1})
    res = manager_client.post("/api/locations/bulk-delete/", {"ids": [used_loc.id, free_loc.id]}, format="json")
    assert res.data["deleted_ids"] == [free_loc.id] and res.data["skipped"][0]["id"] == used_loc.id
    v = VendorFactory()
    assert manager_client.post("/api/vendors/bulk-delete/", {"ids": [v.id]}, format="json").data["deleted"] == 1
    assert not Vendor.objects.filter(pk=v.id).exists() and Location.objects.filter(pk=used_loc.id).exists()
    # Handovers: only cancelled ones go.
    done = Handover.objects.create(type="issue", status="completed")
    cancelled = Handover.objects.create(type="issue", status="cancelled")
    res = manager_client.post("/api/handovers/bulk-delete/", {"ids": [done.id, cancelled.id]}, format="json")
    assert res.data["deleted_ids"] == [cancelled.id]
    # Users are deactivated (admin only), never yourself.
    u = UserFactory()
    assert manager_client.post("/api/users/bulk-delete/", {"ids": [u.id]}, format="json").status_code == 403
    me = User.objects.get(email="admin@test.io")
    res = admin_client.post("/api/users/bulk-delete/", {"ids": [u.id, me.id]}, format="json")
    assert res.data["verb"] == "deactivated" and res.data["deleted_ids"] == [u.id]
    u.refresh_from_db()
    assert u.is_active is False
    # Departments with people are skipped.
    busy, empty = DepartmentFactory(), DepartmentFactory()
    UserFactory(department=busy)
    res = admin_client.post("/api/departments/bulk-delete/", {"ids": [busy.id, empty.id]}, format="json")
    assert res.data["deleted_ids"] == [empty.id]


def test_bulk_status(manager_client, category, employee):
    a = AssetFactory(category=category, custom_data={"ram_gb": 1})
    b = AssetFactory(category=category, status="assigned", assigned_to=employee, custom_data={"ram_gb": 1})
    res = manager_client.post("/api/assets/bulk-status/", {"ids": [a.id, b.id], "status": "retired"}, format="json")
    assert res.data["updated_ids"] == [a.id] and res.data["skipped"][0]["id"] == b.id
    a.refresh_from_db()
    assert a.status == "retired"
    assert manager_client.post("/api/assets/bulk-status/", {"ids": [a.id], "status": "bogus"}, format="json").status_code == 400


# --- CSV export scopes ----------------------------------------------------------------------
def test_export_all_filtered_and_selected(manager_client, employee_client, category):
    a = AssetFactory(category=category, name="Alpha", custom_data={"ram_gb": 1})
    b = AssetFactory(category=category, name="+SUM(1)", custom_data={"ram_gb": 1})
    AssetFactory(category=category, name="Gamma", custom_data={"ram_gb": 1})
    base = "/api/assets/export-table/"
    assert employee_client.get(base, {"file_format": "csv"}).status_code == 403
    all_rows = csv_rows(manager_client.get(base, {"file_format": "csv", "scope": "all", "search": "Alpha"}))
    assert len(all_rows) == 4  # header + 3, filters ignored for "all"
    filtered = csv_rows(manager_client.get(base, {"file_format": "csv", "search": "Alpha"}))
    assert [r[1] for r in filtered[1:]] == ["Alpha"]
    selected = csv_rows(manager_client.get(base, {"file_format": "csv", "scope": "selected", "ids": f"{a.id},{b.id}"}))
    assert sorted(r[1] for r in selected[1:]) == ["'+SUM(1)", "Alpha"]  # formula neutralised
    assert manager_client.get(base, {"file_format": "csv", "scope": "selected"}).status_code == 400


def test_custom_table_export(admin_client, manager_client):
    d = admin_client.post(
        "/api/table-definitions/",
        {"name": "Phones", "singular": "Phone", "columns": [{"name": "Model", "type": "text"}]},
        format="json",
    ).data
    item = TableDefinition.objects.get(pk=d["id"]).sidebar_item_id
    manager_client.post(f"/api/records/?table_item={item}", {"custom_data": {"model": "=HACK()"}}, format="json")
    rows = csv_rows(manager_client.get("/api/records/export-table/", {"table_item": item, "file_format": "csv"}))
    assert rows[0][:2] == ["S.No", "Model"] and rows[1][1] == "'=HACK()"


# --- Bootstrap ---------------------------------------------------------------------------
def test_bootstrap_creates_admin_once(monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_EMAIL", "Boss@Example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "Sup3r!Secret-pass")
    call_command("bootstrap")
    u = User.objects.get(email="boss@example.com")
    assert u.is_superuser and u.role == "admin" and u.check_password("Sup3r!Secret-pass")
    call_command("bootstrap")
    assert User.objects.filter(email="boss@example.com").count() == 1


def test_bootstrap_generates_password_when_unset(monkeypatch, capsys):
    monkeypatch.setenv("ADMIN_EMAIL", "auto@example.com")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    call_command("bootstrap")
    out = capsys.readouterr().out
    assert "Generated admin password:" in out
    password = out.split("Generated admin password:")[1].split()[0]
    assert User.objects.get(email="auto@example.com").check_password(password)
