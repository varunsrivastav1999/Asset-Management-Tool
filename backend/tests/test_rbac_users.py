import pytest

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_employee_cannot_list_users(employee_client):
    assert employee_client.get("/api/users/").status_code == 403


def test_manager_can_list_but_not_create_users(manager_client):
    assert manager_client.get("/api/users/").status_code == 200
    res = manager_client.post("/api/users/", {"email": "x@test.io", "first_name": "X", "last_name": "Y"}, format="json")
    assert res.status_code == 403


def test_admin_creates_user_with_password(admin_client):
    res = admin_client.post(
        "/api/users/",
        {"email": "New@Test.io", "first_name": "New", "last_name": "Hire", "role": "manager", "password": "Sup3r!Secret"},
        format="json",
    )
    assert res.status_code == 201, res.data
    user = User.objects.get(email="new@test.io")
    assert user.role == "manager" and user.check_password("Sup3r!Secret")
    assert "password" not in res.data


def test_admin_rejects_weak_password(admin_client):
    res = admin_client.post(
        "/api/users/", {"email": "w@test.io", "first_name": "W", "last_name": "P", "password": "12345678"}, format="json"
    )
    assert res.status_code == 400


def test_delete_user_deactivates(admin_client, employee):
    assert admin_client.delete(f"/api/users/{employee.id}/").status_code == 204
    employee.refresh_from_db()
    assert employee.is_active is False
    assert admin_client.post(f"/api/users/{employee.id}/activate/").status_code == 200


def test_admin_cannot_deactivate_self(admin_client, admin_user):
    assert admin_client.delete(f"/api/users/{admin_user.id}/").status_code == 400


def test_departments_readable_by_all_writable_by_admin(employee_client, admin_client):
    assert employee_client.get("/api/departments/").status_code == 200
    assert employee_client.post("/api/departments/", {"name": "R&D", "code": "rd"}, format="json").status_code == 403
    res = admin_client.post("/api/departments/", {"name": "R&D", "code": "rd"}, format="json")
    assert res.status_code == 201 and res.data["code"] == "RD"


def test_audit_log_admin_only(admin_client, manager_client):
    assert manager_client.get("/api/audit-logs/").status_code == 403
    assert admin_client.get("/api/audit-logs/").status_code == 200
