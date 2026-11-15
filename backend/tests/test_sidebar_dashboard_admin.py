import pytest

from apps.audit.models import AuditLog
from apps.dashboard.models import DashboardWidget
from apps.navigation.models import SidebarItem

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("seeded_config")]


def names(tree):
    out = []
    for node in tree:
        out.append(node["name"])
        out += names(node.get("children", []))
    return out


# --- Sidebar: reading ------------------------------------------------------------
def test_default_sidebar_is_seeded_by_migration():
    assert SidebarItem.objects.filter(item_type="group").count() == 5
    assert SidebarItem.objects.filter(route="/settings/sidebar").exists()


@pytest.mark.parametrize(
    "client_fixture,visible,hidden",
    [
        ("employee_client", ["Dashboard", "Assets", "Handovers"], ["Receiving", "Catalog", "People", "Audit log", "Settings"]),
        ("manager_client", ["Receiving", "Categories", "People"], ["Audit log", "Settings", "Sidebar"]),
        ("admin_client", ["Audit log", "Settings", "Sidebar", "Dashboard"], []),
    ],
)
def test_sidebar_is_filtered_by_role(request, client_fixture, visible, hidden):
    res = request.getfixturevalue(client_fixture).get("/api/sidebar/")
    assert res.status_code == 200
    got = names(res.data["items"])
    assert all(v in got for v in visible), got
    assert not any(h in got for h in hidden), got


def test_sidebar_hides_inactive_items_empty_groups_and_stray_dividers(employee_client):
    group = SidebarItem.objects.create(name="Empty", item_type="group", visible_roles=["employee"], order=99)
    SidebarItem.objects.create(name="Secret", item_type="page", route="/x", parent=group, visible_roles=["admin"])
    SidebarItem.objects.create(item_type="divider", order=100)
    SidebarItem.objects.filter(name="Scan").update(is_active=False)
    got = employee_client.get("/api/sidebar/").data["items"]
    assert "Empty" not in names(got) and "Scan" not in names(got)
    assert got[-1]["type"] != "divider"


def test_sidebar_requires_authentication(anon_client):
    assert anon_client.get("/api/sidebar/").status_code == 401


# --- Sidebar: management -------------------------------------------------------
def test_only_admin_can_manage_sidebar(manager_client, employee_client, admin_client):
    payload = {
        "name": "Wiki",
        "type": "link",
        "url": "https://wiki.example.com",
        "icon": "book-open",
        "visible_roles": ["employee"],
    }
    assert manager_client.post("/api/sidebar-items/", payload, format="json").status_code == 403
    assert employee_client.get("/api/sidebar-items/").status_code == 403
    res = admin_client.post("/api/sidebar-items/", payload, format="json")
    assert res.status_code == 201, res.data
    assert AuditLog.objects.filter(action="create", model="navigation.sidebaritem").exists()


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"name": "X", "type": "link", "url": "javascript:alert(1)"}, "url"),
        ({"name": "X", "type": "page", "route": "//evil.com"}, "route"),
        ({"name": "X", "type": "page", "route": "assets"}, "route"),
        ({"name": "", "type": "page", "route": "/assets"}, "name"),
        ({"name": "X", "type": "page", "route": "/a", "visible_roles": ["root"]}, "visible_roles"),
        ({"name": "X", "type": "page", "route": "/a", "visible_roles": []}, "visible_roles"),
        ({"name": "X", "type": "page", "route": "/a", "icon": "<svg>"}, "icon"),
    ],
)
def test_sidebar_item_validation(admin_client, payload, field):
    res = admin_client.post("/api/sidebar-items/", payload, format="json")
    assert res.status_code == 400 and field in res.data, res.data


def test_items_can_only_nest_inside_groups(admin_client):
    page = SidebarItem.objects.get(name="Assets")
    res = admin_client.post("/api/sidebar-items/", {"name": "X", "type": "page", "route": "/x", "parent": page.id}, format="json")
    assert res.status_code == 400 and "parent" in res.data


def test_reorder_moves_items_between_groups_and_audits(admin_client, employee_client):
    workflows = SidebarItem.objects.get(name="Workflows")
    scan = SidebarItem.objects.get(name="Scan")
    res = admin_client.post(
        "/api/sidebar-items/reorder/", {"items": [{"id": scan.id, "parent": workflows.id, "order": 0}]}, format="json"
    )
    assert res.status_code == 200, res.data
    scan.refresh_from_db()
    assert scan.parent == workflows
    tree = employee_client.get("/api/sidebar/").data["items"]
    wf = next(g for g in tree if g["name"] == "Workflows")
    assert wf["children"][0]["name"] == "Scan"
    assert AuditLog.objects.filter(action="bulk_update", model="navigation.sidebaritem").exists()


def test_reorder_rejects_cycles_and_non_group_parents(admin_client):
    outer = SidebarItem.objects.create(name="Outer", item_type="group")
    inner = SidebarItem.objects.create(name="Inner", item_type="group", parent=outer)
    res = admin_client.post(
        "/api/sidebar-items/reorder/", {"items": [{"id": outer.id, "parent": inner.id, "order": 0}]}, format="json"
    )
    assert res.status_code == 400
    page = SidebarItem.objects.get(name="Assets")
    res = admin_client.post(
        "/api/sidebar-items/reorder/", {"items": [{"id": outer.id, "parent": page.id, "order": 0}]}, format="json"
    )
    assert res.status_code == 400
    assert (
        admin_client.post("/api/sidebar-items/reorder/", {"items": [{"id": 999999, "order": 0}]}, format="json").status_code
        == 400
    )


def test_reset_restores_defaults(admin_client, manager_client):
    SidebarItem.objects.all().delete()
    assert manager_client.post("/api/sidebar-items/reset/").status_code == 403
    assert admin_client.post("/api/sidebar-items/reset/").data["created"] == 22
    assert admin_client.get("/api/sidebar-items/tree/").data["items"][0]["name"] == "Overview"


# --- Dashboard widgets -----------------------------------------------------------
def test_default_widgets_seeded():
    assert DashboardWidget.objects.count() >= 10


def test_dashboard_is_role_filtered_and_read_only_for_non_admins(employee_client, manager_client, admin_client):
    emp = employee_client.get("/api/dashboard/").data
    sources = {w["data_source"] for w in emp["widgets"]}
    assert "my_assets" in sources and "total_assets" not in sources and "recent_activity" not in sources
    assert emp["can_edit"] is False
    mgr = manager_client.get("/api/dashboard/").data
    assert {"total_assets", "status_breakdown", "recent_activity"} <= {w["data_source"] for w in mgr["widgets"]}
    assert mgr["can_edit"] is False
    assert admin_client.get("/api/dashboard/").data["can_edit"] is True


def test_widget_payload_shapes(manager_client, asset):
    widgets = {w["data_source"]: w for w in manager_client.get("/api/dashboard/").data["widgets"]}
    assert widgets["total_assets"]["data"]["value"] == 1
    chart = widgets["status_breakdown"]["data"]
    assert len(chart["labels"]) == len(chart["datasets"][0]["data"]) == 5
    assert "columns" in widgets["recent_activity"]["data"]


def test_only_admin_can_change_widgets(manager_client, employee_client, admin_client):
    w = DashboardWidget.objects.first()
    for client in (manager_client, employee_client):
        assert client.get("/api/dashboard-widgets/").status_code == 403
        assert client.patch(f"/api/dashboard-widgets/{w.id}/", {"title": "Hacked"}, format="json").status_code == 403
        assert client.delete(f"/api/dashboard-widgets/{w.id}/").status_code == 403
        assert client.post("/api/dashboard-widgets/reorder/", {"ids": [w.id]}, format="json").status_code == 403
    res = admin_client.patch(f"/api/dashboard-widgets/{w.id}/", {"title": "Renamed", "size": "md"}, format="json")
    assert res.status_code == 200 and res.data["title"] == "Renamed"
    assert AuditLog.objects.filter(action="update", model="dashboard.dashboardwidget", object_id=str(w.id)).exists()


def test_org_data_cannot_be_exposed_to_employees(admin_client, employee_client):
    res = admin_client.post(
        "/api/dashboard-widgets/",
        {"title": "Value", "type": "stat", "data_source": "portfolio_value", "visible_roles": ["admin", "employee"]},
        format="json",
    )
    assert res.status_code == 400 and "visible_roles" in res.data
    # Even a hand-edited row is never served to an unauthorised role.
    DashboardWidget.objects.create(title="Leak", widget_type="stat", data_source="portfolio_value", visible_roles=["employee"])
    assert "portfolio_value" not in {w["data_source"] for w in employee_client.get("/api/dashboard/").data["widgets"]}


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"title": "X", "type": "chart", "data_source": "total_assets"}, "data_source"),
        ({"title": "X", "type": "stat", "data_source": "nope"}, "data_source"),
        ({"title": "X", "type": "chart", "data_source": "activity_timeline", "chart_type": "doughnut"}, "chart_type"),
        ({"title": "X", "type": "stat", "data_source": "my_assets", "config": {"tone": "neon"}}, "config"),
        ({"title": " ", "type": "stat", "data_source": "my_assets"}, "title"),
    ],
)
def test_widget_validation(admin_client, payload, field):
    res = admin_client.post("/api/dashboard-widgets/", payload, format="json")
    assert res.status_code == 400 and field in res.data, res.data


def test_widget_create_reorder_delete_reset(admin_client):
    res = admin_client.post(
        "/api/dashboard-widgets/",
        {"title": "Assets by dept", "type": "chart", "data_source": "assets_by_department", "size": "full"},
        format="json",
    )
    assert res.status_code == 201, res.data
    assert res.data["chart_type"] == "bar" and res.data["position"] > 0
    ids = list(DashboardWidget.objects.order_by("position").values_list("id", flat=True))
    new_order = [ids[-1], *ids[:-1]]
    assert admin_client.post("/api/dashboard-widgets/reorder/", {"ids": new_order}, format="json").status_code == 200
    assert DashboardWidget.objects.order_by("position").first().id == ids[-1]
    assert admin_client.post("/api/dashboard-widgets/reorder/", {"ids": new_order[:-1]}, format="json").status_code == 400
    assert admin_client.delete(f"/api/dashboard-widgets/{res.data['id']}/").status_code == 204
    assert admin_client.post("/api/dashboard-widgets/reset/").status_code == 200
    assert admin_client.get("/api/dashboard-widgets/sources/").data["sources"]


# --- Django admin --------------------------------------------------------------
def test_django_admin_is_superuser_only(client, admin_user, manager):
    from django.contrib.auth import get_user_model

    # A staff "admin" role without superuser cannot use the Django admin.
    admin_user.is_staff, admin_user.is_superuser = True, False
    admin_user.save()
    client.force_login(admin_user)
    assert client.get("/admin/").status_code == 302
    su = get_user_model().objects.create_superuser(email="root@test.io", password="x", first_name="R", last_name="T")
    client.force_login(su)
    res = client.get("/admin/")
    assert res.status_code == 200
    for path in (
        "navigation/sidebaritem/",
        "dashboard/dashboardwidget/",
        "assets/asset/",
        "core/counter/",
        "workflows/handoveritem/",
    ):
        assert client.get(f"/admin/{path}").status_code == 200, path
