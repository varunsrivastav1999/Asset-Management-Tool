import csv
import io

import pytest
from openpyxl import load_workbook

from apps.audit.models import AuditLog
from apps.navigation.models import SidebarItem, TableColumn, TablePreference
from apps.navigation.tables import ensure_columns

from .conftest import AssetFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("seeded_config")]


@pytest.fixture
def assets_page():
    item = SidebarItem.objects.get(route="/assets")
    if not item.table:
        item.table = "assets"
        item.save()
    ensure_columns(item)
    return item


def keys(cols, visible_only=True):
    return [c["key"] for c in cols if c["visible"] or not visible_only]


# --- Sidebar colors ------------------------------------------------------------------
def test_admin_sets_colors_and_they_appear_in_everyones_menu(admin_client, employee_client):
    scan = SidebarItem.objects.get(name="Scan")
    res = admin_client.patch(
        f"/api/sidebar-items/{scan.id}/",
        {"color": "#F472B6", "icon_color": "#22d3ee", "active_color": "#a78bfa", "gradient": True, "glow": True},
        format="json",
    )
    assert res.status_code == 200, res.data
    node = next(
        c for g in employee_client.get("/api/sidebar/").data["items"] for c in g.get("children", []) if c["name"] == "Scan"
    )
    assert (node["color"], node["icon_color"], node["active_color"], node["gradient"], node["glow"]) == (
        "#F472B6",
        "#22d3ee",
        "#a78bfa",
        True,
        True,
    )
    assert AuditLog.objects.filter(model="navigation.sidebaritem", object_id=str(scan.id), action="update").exists()


@pytest.mark.parametrize("value", ["red", "#12345", "javascript:alert(1)", "#zzzzzz", "rgb(0,0,0)"])
def test_invalid_colors_rejected(admin_client, value):
    scan = SidebarItem.objects.get(name="Scan")
    assert admin_client.patch(f"/api/sidebar-items/{scan.id}/", {"color": value}, format="json").status_code == 400


def test_pages_get_a_table_automatically(admin_client):
    res = admin_client.post(
        "/api/sidebar-items/", {"name": "Repairs", "type": "page", "route": "/assets?status=in_repair"}, format="json"
    )
    assert res.status_code == 201 and res.data["table"] == "assets"
    link = admin_client.post(
        "/api/sidebar-items/", {"name": "Wiki", "type": "link", "url": "https://w.example", "table": "assets"}, format="json"
    )
    assert link.data["table"] == ""


# --- Column config -----------------------------------------------------------------------
def test_builtin_columns_seeded_with_required_defaults(assets_page, employee_client):
    cols = employee_client.get("/api/tables/assets/columns/").data["columns"]
    assert keys(cols)[:2] == ["sno", "name"]
    assert {"sno", "name", "received_date", "status", "assigned_to"} <= set(keys(cols))
    assert "purchase_cost" not in keys(cols, visible_only=False)  # staff-only column hidden from employees
    names = {c["key"]: c["name"] for c in cols}
    assert names["sno"] == "S.No" and names["name"] == "Item" and names["assigned_to"] == "Assigned To"


def test_list_returns_columns_with_rows(manager_client, assets_page, asset):
    res = manager_client.get("/api/assets/", {"with_columns": 1, "table_item": assets_page.id})
    assert res.status_code == 200
    assert res.data["results"][0]["id"] == asset.id
    assert res.data["table"]["item"] == assets_page.id and res.data["table"]["supports_custom"] is True
    assert keys(res.data["table"]["columns"])[0] == "sno"


def test_only_admin_can_add_edit_delete_columns(admin_client, manager_client, employee_client, assets_page):
    payload = {
        "sidebar_item": assets_page.id,
        "name": "Cost centre",
        "type": "select",
        "options": ["CC1", "CC2"],
        "is_searchable": True,
        "is_sortable": True,
    }
    for client in (manager_client, employee_client):
        assert client.post("/api/table-columns/", payload, format="json").status_code == 403
    res = admin_client.post("/api/table-columns/", payload, format="json")
    assert res.status_code == 201, res.data
    assert res.data["key"] == "cost_centre" and not res.data["is_builtin"]
    col_id = res.data["id"]
    assert manager_client.patch(f"/api/table-columns/{col_id}/", {"name": "x"}, format="json").status_code == 403
    assert admin_client.patch(f"/api/table-columns/{col_id}/", {"name": "Cost center"}, format="json").status_code == 200
    assert AuditLog.objects.filter(model="navigation.tablecolumn", action__in=["create", "update"]).count() >= 2
    assert admin_client.delete(f"/api/table-columns/{col_id}/").status_code == 204


def test_builtins_can_be_renamed_and_hidden_but_not_deleted_or_retyped(admin_client, assets_page):
    status = TableColumn.objects.get(sidebar_item=assets_page, key="status")
    assert (
        admin_client.patch(f"/api/table-columns/{status.id}/", {"name": "State", "is_visible": False}, format="json").status_code
        == 200
    )
    assert admin_client.patch(f"/api/table-columns/{status.id}/", {"type": "text"}, format="json").status_code == 400
    assert admin_client.delete(f"/api/table-columns/{status.id}/").status_code == 400
    sno = TableColumn.objects.get(sidebar_item=assets_page, key="sno")
    assert admin_client.patch(f"/api/table-columns/{sno.id}/", {"is_sortable": True}, format="json").status_code == 400


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"name": "Item", "key": "name"}, "key"),  # reserved by a built-in
        ({"name": "Bad key", "key": "Bad Key!"}, "key"),
        ({"name": "Pick", "type": "select", "options": []}, "options"),
        ({"name": "Seq", "type": "auto_number"}, "type"),
        ({"name": " "}, "name"),
        ({"name": "W", "width": 5}, "width"),
    ],
)
def test_column_validation(admin_client, assets_page, payload, field):
    res = admin_client.post("/api/table-columns/", {"sidebar_item": assets_page.id, **payload}, format="json")
    assert res.status_code == 400 and field in res.data, res.data


def test_custom_columns_not_allowed_on_tables_without_custom_data(admin_client):
    users_page = SidebarItem.objects.get(route="/people/users")
    res = admin_client.post("/api/table-columns/", {"sidebar_item": users_page.id, "name": "Shirt size"}, format="json")
    assert res.status_code == 400


def test_reorder_and_reset(admin_client, assets_page):
    ids = list(TableColumn.objects.filter(sidebar_item=assets_page).order_by("order").values_list("id", flat=True))
    new = [ids[-1], *ids[:-1]]
    assert (
        admin_client.post("/api/table-columns/reorder/", {"sidebar_item": assets_page.id, "ids": new}, format="json").status_code
        == 200
    )
    assert TableColumn.objects.filter(sidebar_item=assets_page).order_by("order").first().id == ids[-1]
    assert (
        admin_client.post(
            "/api/table-columns/reorder/", {"sidebar_item": assets_page.id, "ids": new[:-1]}, format="json"
        ).status_code
        == 400
    )
    TableColumn.objects.create(sidebar_item=assets_page, name="Extra", key="extra")
    assert admin_client.post("/api/table-columns/reset/", {"sidebar_item": assets_page.id}, format="json").status_code == 200
    assert not TableColumn.objects.filter(sidebar_item=assets_page, key="extra").exists()


# --- Custom values, search, sort, filter, export --------------------------------------------
@pytest.fixture
def cost_centre(assets_page):
    return TableColumn.objects.create(
        sidebar_item=assets_page,
        name="Cost centre",
        key="cost_centre",
        column_type="select",
        options=["CC1", "CC2"],
        is_searchable=True,
        is_sortable=True,
        order=99,
    )


def test_custom_values_are_validated_stored_and_survive_asset_edits(manager_client, employee_client, category, cost_centre):
    a = AssetFactory(category=category, custom_data={"ram_gb": 8})
    assert employee_client.patch(f"/api/assets/{a.id}/custom-data/", {"cost_centre": "CC1"}, format="json").status_code == 403
    assert manager_client.patch(f"/api/assets/{a.id}/custom-data/", {"cost_centre": "CC9"}, format="json").status_code == 400
    assert manager_client.patch(f"/api/assets/{a.id}/custom-data/", {"nope": "x"}, format="json").status_code == 400
    res = manager_client.patch(f"/api/assets/{a.id}/custom-data/", {"cost_centre": "CC1"}, format="json")
    assert res.status_code == 200 and res.data["custom_data"] == {"ram_gb": 8, "cost_centre": "CC1"}
    # Editing category fields through the asset form must not wipe table-column values.
    assert manager_client.patch(f"/api/assets/{a.id}/", {"custom_data": {"ram_gb": 32}}, format="json").status_code == 200
    a.refresh_from_db()
    assert a.custom_data == {"ram_gb": 32, "cost_centre": "CC1"}
    assert AuditLog.objects.filter(model="assets.asset", object_id=str(a.id), changes__has_key="custom_data").exists()


def test_search_sort_and_filter_follow_the_column_config(manager_client, category, assets_page, cost_centre):
    a = AssetFactory(category=category, name="Alpha", custom_data={"ram_gb": 1, "cost_centre": "CC2"})
    b = AssetFactory(category=category, name="Beta", custom_data={"ram_gb": 1, "cost_centre": "CC1"})
    params = {"table_item": assets_page.id}
    # Custom searchable column
    assert [r["id"] for r in manager_client.get("/api/assets/", {**params, "search": "CC2"}).data["results"]] == [a.id]
    # Making a column unsearchable removes it from search
    cost_centre.is_searchable = False
    cost_centre.save()
    assert manager_client.get("/api/assets/", {**params, "search": "CC2"}).data["count"] == 0
    # Sort by custom key and by built-in expression
    assert [r["id"] for r in manager_client.get("/api/assets/", {**params, "ordering": "cost_centre"}).data["results"]] == [
        b.id,
        a.id,
    ]
    assert [r["id"] for r in manager_client.get("/api/assets/", {**params, "ordering": "-name"}).data["results"]] == [b.id, a.id]
    # Filter on a custom column
    assert [r["id"] for r in manager_client.get("/api/assets/", {**params, "cf.cost_centre": "CC1"}).data["results"]] == [b.id]


def test_search_respects_column_roles(employee_client, employee, category, assets_page):
    AssetFactory(
        category=category,
        name="Mine",
        serial_number="SER-XYZ",
        assigned_to=employee,
        status="assigned",
        custom_data={"ram_gb": 1},
    )
    serial = TableColumn.objects.get(sidebar_item=assets_page, key="serial_number")
    assert employee_client.get("/api/assets/", {"search": "SER-XYZ"}).data["count"] == 1
    serial.visible_roles = ["admin", "manager"]
    serial.save()
    name = TableColumn.objects.get(sidebar_item=assets_page, key="name")
    name.is_searchable = False
    name.save()
    assert employee_client.get("/api/assets/", {"search": "SER-XYZ"}).data["count"] == 0


def test_export_uses_visible_columns_in_order_with_custom_names(manager_client, manager, category, assets_page, cost_centre):
    AssetFactory(category=category, name="=cmd()", custom_data={"ram_gb": 1, "cost_centre": "CC1"})
    TableColumn.objects.filter(sidebar_item=assets_page, key="status").update(name="State")
    TableColumn.objects.filter(sidebar_item=assets_page, key="warranty_expiry").update(is_visible=False)
    TablePreference.objects.create(user=manager, sidebar_item=assets_page, hidden=["received_date"], shown=[])
    res = manager_client.get("/api/assets/export-table/", {"table_item": assets_page.id, "file_format": "csv"})
    assert res.status_code == 200
    rows = list(csv.reader(io.StringIO(res.content.decode("utf-8-sig"))))
    assert rows[0] == ["S.No", "Item", "State", "Assigned To", "Cost centre"]
    assert rows[1][0] == "1" and rows[1][1] == "'=cmd()" and rows[1][-1] == "CC1"
    xlsx = manager_client.get("/api/assets/export-table/", {"table_item": assets_page.id})
    assert load_workbook(io.BytesIO(xlsx.content)).active["B1"].value == "Item"


def test_every_configured_table_lists_with_columns(admin_client):
    for item in SidebarItem.objects.exclude(table=""):
        res = admin_client.get(f"/api/tables/{item.table}/columns/", {"item": item.id})
        assert res.status_code == 200 and res.data["columns"], item.table


# --- Per-user visibility ---------------------------------------------------------------
def test_users_toggle_their_own_columns_only(employee_client, client_for, assets_page, employee):
    res = employee_client.put(
        "/api/tables/prefs/", {"item": assets_page.id, "hidden": ["status", "sno"], "shown": ["serial_number"]}, format="json"
    )
    assert res.status_code == 200
    assert res.data["hidden"] == ["status"]  # required columns can't be hidden
    cols = {c["key"]: c["visible"] for c in res.data["columns"]}
    assert cols["status"] is False and cols["serial_number"] is True and cols["sno"] is True
    other = client_for(UserFactory())
    other_cols = {c["key"]: c["visible"] for c in other.get("/api/tables/assets/columns/").data["columns"]}
    assert other_cols["status"] is True and other_cols["serial_number"] is False
    assert employee_client.delete(f"/api/tables/prefs/?item={assets_page.id}").status_code == 204
    assert not TablePreference.objects.filter(user=employee).exists()


def test_column_admin_endpoints_admin_only(manager_client, employee_client):
    for c in (manager_client, employee_client):
        assert c.get("/api/table-columns/").status_code == 403
    assert manager_client.get("/api/tables/").status_code == 200
