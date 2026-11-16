import pytest

from apps.dashboard.models import DashboardWidget
from apps.navigation.models import SidebarItem

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("seeded_config")]


@pytest.fixture
def table(admin_client, manager_client):
    t = admin_client.post(
        "/api/table-definitions/",
        {
            "name": "Tickets",
            "singular": "Ticket",
            "columns": [
                {"name": "Title"},
                {"name": "State", "type": "status"},
                {"name": "Urgent", "type": "boolean"},
                {"name": "Note"},
            ],
        },
        format="json",
    ).data
    url = f"/api/records/?table_item={t['sidebar_item']}"
    for title, state, urgent in [("A", "Open", True), ("B", "Open", False), ("C", "Done", None)]:
        data = {"title": title, "state": state} | ({"urgent": urgent} if urgent is not None else {})
        assert manager_client.post(url, {"custom_data": data}, format="json").status_code == 201
    return t


def widget(admin_client, source, kind, roles=("admin", "manager", "employee"), **extra):
    return admin_client.post(
        "/api/dashboard-widgets/",
        {"title": source, "type": kind, "data_source": source, "visible_roles": list(roles), "size": "md", **extra},
        format="json",
    )


def test_catalog_lists_sources_for_each_custom_table(admin_client, table):
    sources = {s["key"]: s for s in admin_client.get("/api/dashboard-widgets/sources/").data["sources"]}
    tid = table["id"]
    assert sources[f"table:{tid}:count"]["types"] == ["stat"] and sources[f"table:{tid}:count"]["group"] == "Table: Tickets"
    assert sources[f"table:{tid}:latest"]["types"] == ["table"]
    assert sources[f"table:{tid}:by:state"]["label"] == "Tickets by State"
    assert f"table:{tid}:by:urgent" in sources
    assert f"table:{tid}:by:note" not in sources  # free text can't be grouped
    assert "total_assets" in sources  # the fixed sources are still there


def test_table_widgets_render_on_everyones_dashboard(admin_client, employee_client, table):
    tid = table["id"]
    res = widget(admin_client, f"table:{tid}:count", "stat")
    assert res.status_code == 201, res.data
    assert widget(admin_client, f"table:{tid}:by:state", "chart", chart_type="doughnut").status_code == 201
    assert widget(admin_client, f"table:{tid}:latest", "table").status_code == 201
    data = {w["data_source"]: w["data"] for w in employee_client.get("/api/dashboard/").data["widgets"]}
    assert data[f"table:{tid}:count"]["value"] == 3 and data[f"table:{tid}:count"]["link"] == "/t/tickets"
    chart = data[f"table:{tid}:by:state"]
    assert dict(zip(chart["labels"], chart["datasets"][0]["data"], strict=True)) == {"Open": 2, "Done": 1}
    assert chart["labels"][:2] == ["Open", "Done"]  # status order, not alphabetical
    latest = data[f"table:{tid}:latest"]["rows"]
    assert [r["title"] for r in latest] == ["C", "B", "A"] and latest[0]["link"].startswith("/t/tickets?open=")


def test_yes_no_groups_include_unset(admin_client, admin_user, table):
    from apps.dashboard.sources import DataContext, resolve

    chart = resolve(f"table:{table['id']}:by:urgent", DataContext(admin_user))
    assert dict(zip(chart["labels"], chart["datasets"][0]["data"], strict=True)) == {"Yes": 1, "No": 1, "Not set": 1}


def test_table_widgets_follow_the_tables_visibility(admin_client, employee_client, manager_client, table):
    item = SidebarItem.objects.get(pk=table["sidebar_item"])
    item.visible_roles = ["admin", "manager"]
    item.save()
    res = widget(admin_client, f"table:{table['id']}:count", "stat")
    assert res.status_code == 400 and "can't see" in str(res.data["visible_roles"])
    assert widget(admin_client, f"table:{table['id']}:count", "stat", roles=("admin", "manager")).status_code == 201
    assert any(w["data_source"].startswith("table:") for w in manager_client.get("/api/dashboard/").data["widgets"])
    # Defence in depth: even a hand-edited widget row is not served to employees.
    DashboardWidget.objects.filter(data_source__startswith="table:").update(visible_roles=["admin", "manager", "employee"])
    assert not any(w["data_source"].startswith("table:") for w in employee_client.get("/api/dashboard/").data["widgets"])


def test_widgets_of_a_deleted_table_disappear(admin_client, manager_client, table):
    widget(admin_client, f"table:{table['id']}:count", "stat")
    manager_client.post(f"/api/records/bulk-archive/?table_item={table['sidebar_item']}", {"all": True}, format="json")
    assert admin_client.delete(f"/api/table-definitions/{table['id']}/").status_code == 204
    assert not any(w["data_source"].startswith("table:") for w in admin_client.get("/api/dashboard/").data["widgets"])
    assert widget(admin_client, f"table:{table['id']}:count", "stat").status_code == 400  # unknown source now


@pytest.mark.parametrize("bad", ["table:x:count", "table:1:by", "table:1:nope", "table::count", "tables:1:count"])
def test_malformed_table_sources_are_rejected(admin_client, bad):
    assert widget(admin_client, bad, "stat").status_code == 400
