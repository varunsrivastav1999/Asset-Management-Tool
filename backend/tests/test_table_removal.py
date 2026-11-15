"""Every way a table can be removed, and what must (and must not) happen to its rows, columns, menu and rules."""

import pytest

from apps.assets.models import Asset, Vendor
from apps.audit.models import AuditLog
from apps.navigation.models import SidebarItem, TableColumn, TableDefinition, TablePreference, TableRecord
from apps.reminders.models import ReminderRule, ReminderTemplate

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("seeded_config")]


def make_table(admin_client, name, *, parent=None, columns=None):
    payload = {"name": name, "singular": name.rstrip("s")}
    if parent is not None:
        payload["parent"] = parent
    if columns:
        payload["columns"] = columns
    res = admin_client.post("/api/table-definitions/", payload, format="json")
    assert res.status_code == 201, res.data
    return res.data


def add_rows(client, item_id, n, prefix="Row"):
    url = f"/api/records/?table_item={item_id}"
    return [client.post(url, {"custom_data": {"name": f"{prefix} {i}"}}, format="json").data["id"] for i in range(n)]


def leftovers(item_id, defn_id):
    return {
        "menu": SidebarItem.objects.filter(pk=item_id).exists(),
        "definition": TableDefinition.objects.filter(pk=defn_id).exists(),
        "columns": TableColumn.objects.filter(sidebar_item_id=item_id).count(),
        "prefs": TablePreference.objects.filter(sidebar_item_id=item_id).count(),
    }


GONE = {"menu": False, "definition": False, "columns": 0, "prefs": 0}


# --- Empty custom tables -------------------------------------------------------------------
@pytest.mark.parametrize("via", ["tables", "menu"])
def test_empty_custom_table_is_removed_completely(admin_client, manager_client, via):
    t = make_table(admin_client, "Keys")
    item = t["sidebar_item"]
    manager_client.patch("/api/tables/prefs/", {"item": item, "hidden": ["created_at"]}, format="json")
    assert admin_client.get(f"/api/table-definitions/{t['id']}/delete-check/").data == {
        "can_delete": True,
        "reason": None,
        "row_count": 0,
    }
    url = f"/api/table-definitions/{t['id']}/" if via == "tables" else f"/api/sidebar-items/{item}/"
    assert admin_client.delete(url).status_code == 204
    assert leftovers(item, t["id"]) == GONE
    # Its records endpoint, menu entry and listing are gone; deleting again is a clean 404.
    assert manager_client.get(f"/api/records/?table_item={item}").status_code == 404
    assert all(i.get("id") != item for g in admin_client.get("/api/sidebar/").data["items"] for i in [g, *g.get("children", [])])
    assert t["id"] not in [d["id"] for d in admin_client.get("/api/table-definitions/").data]
    assert admin_client.delete(url).status_code == 404
    assert AuditLog.objects.filter(action="delete").exists()


def test_name_and_address_can_be_reused_after_delete(admin_client):
    first = make_table(admin_client, "Badges")
    admin_client.delete(f"/api/table-definitions/{first['id']}/")
    again = make_table(admin_client, "Badges")
    assert again["route"] == first["route"] == "/t/badges"


# --- Custom tables with rows -----------------------------------------------------------------
def test_table_with_rows_is_protected_on_both_screens(admin_client, manager_client):
    t = make_table(admin_client, "Licences")
    item = t["sidebar_item"]
    add_rows(manager_client, item, 2)
    check = admin_client.get(f"/api/table-definitions/{t['id']}/delete-check/").data
    assert check["can_delete"] is False and check["row_count"] == 2 and "2 record" in check["reason"]
    for url in (f"/api/table-definitions/{t['id']}/", f"/api/sidebar-items/{item}/"):
        res = admin_client.delete(url)
        assert res.status_code == 400 and res.data["code"] == "has_data"
    assert leftovers(item, t["id"])["definition"] and TableRecord.objects.filter(definition_id=t["id"]).count() == 2


def test_archived_rows_dont_block_and_are_kept_after_delete(admin_client, manager_client):
    t = make_table(admin_client, "Phones")
    item = t["sidebar_item"]
    ids = add_rows(manager_client, item, 3)
    manager_client.post(f"/api/records/bulk-archive/?table_item={item}", {"all": True}, format="json")
    assert admin_client.get(f"/api/table-definitions/{t['id']}/delete-check/").data["can_delete"] is True
    assert admin_client.delete(f"/api/sidebar-items/{item}/").status_code == 204
    kept = TableRecord.objects.filter(pk__in=ids)
    assert kept.count() == 3 and all(r.is_archived and r.archived_from == "Phones" and r.definition_id is None for r in kept)


def test_moving_rows_out_unblocks_delete_and_keeps_them_live(admin_client, manager_client):
    src, dst = make_table(admin_client, "Old kit"), make_table(admin_client, "New kit")
    ids = add_rows(manager_client, src["sidebar_item"], 2)
    moved = manager_client.post(
        f"/api/records/bulk-move/?table_item={src['sidebar_item']}", {"all": True, "target": dst["id"]}, format="json"
    )
    assert moved.data["moved"] == 2
    assert admin_client.delete(f"/api/table-definitions/{src['id']}/").status_code == 204
    assert manager_client.get(f"/api/records/?table_item={dst['sidebar_item']}").data["count"] == 2
    assert set(TableRecord.objects.filter(pk__in=ids).values_list("definition_id", flat=True)) == {dst["id"]}


# --- Groups ----------------------------------------------------------------------------------
def test_group_with_a_non_empty_table_is_not_deleted_at_all(admin_client, manager_client):
    group = admin_client.post("/api/sidebar-items/", {"name": "Ops", "type": "group"}, format="json").data
    empty = make_table(admin_client, "Spare", parent=group["id"])
    full = make_table(admin_client, "Busy", parent=group["id"])
    add_rows(manager_client, full["sidebar_item"], 1)
    res = admin_client.delete(f"/api/sidebar-items/{group['id']}/")
    assert res.status_code == 400 and "Busy" in res.data["detail"]
    # All or nothing: the group, both tables and their columns are untouched.
    assert SidebarItem.objects.filter(pk=group["id"]).exists()
    assert leftovers(empty["sidebar_item"], empty["id"])["definition"]
    assert leftovers(full["sidebar_item"], full["id"])["definition"]


def test_group_with_empty_tables_removes_everything_inside(admin_client):
    group = admin_client.post("/api/sidebar-items/", {"name": "Lab", "type": "group"}, format="json").data
    sub = admin_client.post("/api/sidebar-items/", {"name": "Sub", "type": "group", "parent": group["id"]}, format="json").data
    a = make_table(admin_client, "Probes", parent=group["id"])
    b = make_table(admin_client, "Cables", parent=sub["id"])
    assert admin_client.delete(f"/api/sidebar-items/{group['id']}/").status_code == 204
    assert leftovers(a["sidebar_item"], a["id"]) == GONE and leftovers(b["sidebar_item"], b["id"]) == GONE
    assert not SidebarItem.objects.filter(pk__in=[group["id"], sub["id"]]).exists()


# --- Built-in tables ---------------------------------------------------------------------------
def test_builtin_data_is_never_deleted_with_a_page(admin_client, asset):
    extra = admin_client.post(
        "/api/sidebar-items/",
        {"name": "Repairs", "type": "page", "route": "/assets?status=in_repair", "table": "assets"},
        format="json",
    ).data
    assert admin_client.delete(f"/api/sidebar-items/{extra['id']}/").status_code == 204
    assert Asset.objects.filter(pk=asset.pk).exists()
    last = TableDefinition.objects.get(source="assets")
    assert admin_client.delete(f"/api/table-definitions/{last.id}/").status_code == 400  # last page, has rows


def test_last_page_of_an_empty_builtin_table_can_go_and_reset_brings_it_back(admin_client):
    assert not Vendor.objects.exists()
    vendors = TableDefinition.objects.get(source="vendors")
    assert admin_client.delete(f"/api/table-definitions/{vendors.id}/").status_code == 204
    assert not TableDefinition.objects.filter(source="vendors").exists()
    admin_client.post("/api/sidebar-items/reset/")
    restored = TableDefinition.objects.get(source="vendors")
    assert TableColumn.objects.filter(sidebar_item_id=restored.sidebar_item_id).exists()


# --- Side effects --------------------------------------------------------------------------------
def test_reminder_rules_of_a_deleted_table_are_paused_not_lost(admin_client):
    t = make_table(admin_client, "Contracts")
    template = ReminderTemplate.objects.create(name="Contract ending", subject="s", body="b")
    rule = ReminderRule.objects.create(
        name="Contract ends",
        section_id=t["sidebar_item"],
        trigger="manual",
        channels=["in_app"],
        recipients={"types": ["managers"]},
        schedule={"kind": "manual"},
        template=template,
        is_active=True,
    )
    assert admin_client.delete(f"/api/table-definitions/{t['id']}/").status_code == 204
    rule.refresh_from_db()
    assert rule.section_id is None and rule.is_active is False


def test_only_admins_can_remove_tables(manager_client, employee_client, admin_client):
    t = make_table(admin_client, "Secrets")
    for c in (manager_client, employee_client):
        assert c.delete(f"/api/table-definitions/{t['id']}/").status_code == 403
        assert c.delete(f"/api/sidebar-items/{t['sidebar_item']}/").status_code == 403
        assert c.get(f"/api/table-definitions/{t['id']}/delete-check/").status_code == 403
    assert TableDefinition.objects.filter(pk=t["id"]).exists()
