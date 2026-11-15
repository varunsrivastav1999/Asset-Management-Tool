import pytest
from django.conf import settings

from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

COOKIE = settings.JWT_REFRESH_COOKIE["name"]


def login(client, email, password="Str0ng!Passw0rd"):
    return client.post("/api/auth/login/", {"email": email, "password": password}, format="json")


def test_login_returns_access_and_sets_httponly_refresh_cookie(anon_client, employee):
    res = login(anon_client, employee.email.upper())
    assert res.status_code == 200
    assert res.data["access"]
    assert res.data["user"]["email"] == employee.email
    cookie = res.cookies[COOKIE]
    assert cookie["httponly"]
    assert cookie["samesite"] == "Strict"
    assert cookie["path"] == "/api/auth/"
    assert "refresh" not in res.data
    assert AuditLog.objects.filter(action="login", actor=employee).exists()


def test_login_wrong_password_is_rejected_and_audited(anon_client, employee):
    res = login(anon_client, employee.email, "nope")
    assert res.status_code == 401
    assert AuditLog.objects.filter(action="login_failed", object_repr=employee.email).exists()


def test_inactive_user_cannot_login(anon_client, employee):
    employee.is_active = False
    employee.save()
    assert login(anon_client, employee.email).status_code == 401


def test_refresh_rotates_cookie_and_old_token_is_blacklisted(anon_client, employee):
    login(anon_client, employee.email)
    old = anon_client.cookies[COOKIE].value
    res = anon_client.post("/api/auth/refresh/")
    assert res.status_code == 200
    assert res.data["access"] and res.data["user"]["id"] == employee.id
    new = res.cookies[COOKIE].value
    assert new != old
    anon_client.cookies[COOKIE] = old
    assert anon_client.post("/api/auth/refresh/").status_code == 401


def test_refresh_without_cookie(anon_client):
    assert anon_client.post("/api/auth/refresh/").status_code == 401


def test_logout_blacklists_refresh(anon_client, employee):
    login(anon_client, employee.email)
    token = anon_client.cookies[COOKIE].value
    assert anon_client.post("/api/auth/logout/").status_code == 204
    anon_client.cookies[COOKIE] = token
    assert anon_client.post("/api/auth/refresh/").status_code == 401


def test_me_and_profile_update_cannot_escalate_role(employee_client, employee):
    res = employee_client.patch("/api/auth/me/", {"phone": "555-0101", "role": "admin"}, format="json")
    assert res.status_code == 200
    employee.refresh_from_db()
    assert employee.phone == "555-0101"
    assert employee.role == "employee"


def test_change_password(employee_client, employee):
    res = employee_client.post(
        "/api/auth/change-password/", {"current_password": "Str0ng!Passw0rd", "new_password": "An0ther!Secret9"}, format="json"
    )
    assert res.status_code == 204
    employee.refresh_from_db()
    assert employee.check_password("An0ther!Secret9")


def test_change_password_requires_current(employee_client):
    res = employee_client.post(
        "/api/auth/change-password/", {"current_password": "bad", "new_password": "An0ther!Secret9"}, format="json"
    )
    assert res.status_code == 400


def test_unauthenticated_requests_are_rejected(anon_client):
    assert anon_client.get("/api/assets/").status_code == 401


def test_health_endpoints(anon_client):
    assert anon_client.get("/api/health/").json() == {"status": "ok"}
    res = anon_client.get("/api/health/ready/")
    assert res.status_code == 200
    assert res.json()["checks"]["database"] == "ok"
    assert res["X-Request-ID"]
