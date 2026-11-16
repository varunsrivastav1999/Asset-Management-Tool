import os
import time

import pytest

from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def backup_dir(settings, tmp_path):
    settings.BACKUP_DIR = str(tmp_path)
    (tmp_path / "auto-20261115-020000.dump").write_bytes(b"PGDMP-old")
    (tmp_path / "manual-20261116-101500.dump").write_bytes(b"PGDMP-new!")
    os.utime(tmp_path / "auto-20261115-020000.dump", (1_700_000_000, 1_700_000_000))  # older
    (tmp_path / "manual-20261116-101600.dump.part").write_bytes(b"in progress")  # not finished: hidden
    (tmp_path / "notes.txt").write_text("ignore me")
    return tmp_path


def test_admin_lists_backups_newest_first(admin_client, backup_dir):
    (backup_dir / ".heartbeat").write_text(str(int(time.time())))
    data = admin_client.get("/api/backups/").json()
    assert [b["name"] for b in data["backups"]] == ["manual-20261116-101500.dump", "auto-20261115-020000.dump"]
    assert {b["kind"] for b in data["backups"]} == {"auto", "manual"}
    assert data["service_online"] is True and data["pending"] == 0 and data["keep"] == 7


def test_service_offline_without_recent_heartbeat(admin_client, backup_dir):
    (backup_dir / ".heartbeat").write_text(str(int(time.time()) - 600))
    assert admin_client.get("/api/backups/").json()["service_online"] is False


def test_backup_now_queues_a_request_for_the_service(admin_client, backup_dir):
    res = admin_client.post("/api/backups/")
    assert res.status_code == 202 and res.json()["pending"] == 1
    assert len(list((backup_dir / ".requests").iterdir())) == 1
    assert AuditLog.objects.filter(model="core.backup", action="create").exists()


def test_download_and_delete(admin_client, backup_dir):
    res = admin_client.get("/api/backups/manual-20261116-101500.dump/")
    assert res.status_code == 200 and b"".join(res.streaming_content) == b"PGDMP-new!"
    assert "attachment" in res["Content-Disposition"]
    assert admin_client.delete("/api/backups/manual-20261116-101500.dump/").status_code == 204
    assert not (backup_dir / "manual-20261116-101500.dump").exists()
    assert admin_client.delete("/api/backups/manual-20261116-101500.dump/").status_code == 404


@pytest.mark.parametrize("name", ["notes.txt", "..%2Fsecret.dump", "manual-20261116-101600.dump.part", "x.dump"])
def test_only_backup_files_can_be_reached(admin_client, backup_dir, name):
    assert admin_client.get(f"/api/backups/{name}/").status_code == 404


def test_backups_are_admin_only(manager_client, employee_client, anon_client, backup_dir):
    for c in (manager_client, employee_client):
        assert c.get("/api/backups/").status_code == 403
        assert c.post("/api/backups/").status_code == 403
        assert c.get("/api/backups/auto-20261115-020000.dump/").status_code == 403
    assert anon_client.get("/api/backups/").status_code == 401


def test_unwritable_backup_folder_gives_a_clear_error(admin_client, settings, tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file in the way")
    settings.BACKUP_DIR = str(blocker)
    res = admin_client.post("/api/backups/")
    assert res.status_code == 503 and "backup service" in res.json()["detail"]


# --- Uploads -----------------------------------------------------------------------------------
def dump_file(name="prod.dump", body=b"PGDMP\x01\x0e\x00 rest of a real dump"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, body, content_type="application/octet-stream")


def test_admin_uploads_a_backup_and_can_download_it(admin_client, backup_dir):
    res = admin_client.post("/api/backups/upload/", {"file": dump_file()})
    assert res.status_code == 201, res.data
    name = res.data["name"]
    assert name.startswith("uploaded-") and name.endswith(".dump") and res.data["kind"] == "uploaded"
    assert (backup_dir / name).read_bytes().startswith(b"PGDMP")
    assert not list(backup_dir.glob(".*.part"))  # written atomically, no leftovers
    listed = [b["name"] for b in admin_client.get("/api/backups/").json()["backups"]]
    assert name in listed
    assert b"".join(admin_client.get(f"/api/backups/{name}/").streaming_content).startswith(b"PGDMP")
    assert AuditLog.objects.filter(model="core.backup", object_repr__startswith="Uploaded backup").exists()


def test_two_uploads_in_the_same_second_get_different_names(admin_client, backup_dir):
    a = admin_client.post("/api/backups/upload/", {"file": dump_file()}).data["name"]
    b = admin_client.post("/api/backups/upload/", {"file": dump_file()}).data["name"]
    assert a != b


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("notes.dump", b"just text, not a dump"),  # wrong content
        ("backup.sql", b"PGDMP but wrong extension"),
        ("../../etc/passwd.dump", b"nope"),
    ],
)
def test_upload_rejects_anything_but_a_pg_dump(admin_client, backup_dir, name, body):
    res = admin_client.post("/api/backups/upload/", {"file": dump_file(name, body)})
    assert res.status_code == 400
    assert not [p for p in backup_dir.iterdir() if p.name.startswith("uploaded-")]


def test_upload_size_limit(admin_client, backup_dir, settings):
    settings.BACKUP_UPLOAD_MAX_MB = 0
    assert admin_client.post("/api/backups/upload/", {"file": dump_file()}).status_code == 400


def test_upload_is_admin_only(manager_client, employee_client, anon_client, backup_dir):
    for c in (manager_client, employee_client):
        assert c.post("/api/backups/upload/", {"file": dump_file()}).status_code == 403
    assert anon_client.post("/api/backups/upload/", {"file": dump_file()}).status_code == 401


# --- restore ------------------------------------------------------------------------------------------------------

RESTORE_URL = "/api/backups/manual-20261116-101500.dump/restore/"


@pytest.fixture
def online(backup_dir):
    (backup_dir / ".heartbeat").write_text(str(int(time.time())))
    return backup_dir


def test_restore_queues_a_request_for_the_service(admin_client, online):
    res = admin_client.post(RESTORE_URL, {"confirm": "manual-20261116-101500.dump"}, format="json")
    assert res.status_code == 202
    assert res.json()["restore"] == {
        "state": "queued",
        "name": "manual-20261116-101500.dump",
        "message": "Waiting for the backup service",
        "at": None,
        "id": None,
    }
    assert (online / ".restore-request").read_text().strip() == "manual-20261116-101500.dump"
    assert AuditLog.objects.filter(model="core.backup", object_repr__startswith="Restore of").exists()


def test_restore_needs_the_name_typed_to_confirm(admin_client, online):
    res = admin_client.post(RESTORE_URL, {"confirm": "yes"}, format="json")
    assert res.status_code == 400 and res.json()["code"] == "confirm_required"
    assert not (online / ".restore-request").exists()


def test_only_one_restore_at_a_time(admin_client, online):
    confirm = {"confirm": "manual-20261116-101500.dump"}
    assert admin_client.post(RESTORE_URL, confirm, format="json").status_code == 202
    assert admin_client.post(RESTORE_URL, confirm, format="json").status_code == 409
    (online / ".restore-request").unlink()
    (online / ".restore-state").write_text('{"state": "running", "name": "x", "message": "Loading", "at": 1, "id": "a"}')
    assert admin_client.post(RESTORE_URL, confirm, format="json").status_code == 409


def test_restore_refused_when_service_is_down_or_backup_missing(admin_client, backup_dir):
    confirm = {"confirm": "manual-20261116-101500.dump"}
    assert admin_client.post(RESTORE_URL, confirm, format="json").status_code == 503
    (backup_dir / ".heartbeat").write_text(str(int(time.time())))
    missing = "/api/backups/manual-20200101-000000.dump/restore/"
    assert admin_client.post(missing, {"confirm": "manual-20200101-000000.dump"}, format="json").status_code == 404


def test_status_reports_finished_restore_and_migrates_once(admin_client, online, monkeypatch):
    from apps.core import views

    calls = []
    monkeypatch.setattr(views, "call_command", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(views.MigrationExecutor, "migration_plan", lambda self, targets: ["pending"])
    (online / ".restore-state").write_text(
        '{"state": "done", "name": "manual-20261116-101500.dump", "message": "Restored", "at": 1, "id": "r1"}'
    )
    for _ in range(2):
        assert admin_client.get("/api/backups/").json()["restore"]["state"] == "done"
    assert calls == [("migrate",)]


def test_safety_backups_are_listed(admin_client, online):
    (online / "safety-20261116-120000.dump").write_bytes(b"PGDMP")
    kinds = {b["name"]: b["kind"] for b in admin_client.get("/api/backups/").json()["backups"]}
    assert kinds["safety-20261116-120000.dump"] == "safety"


def test_restore_is_admin_only(manager_client, employee_client, anon_client, online):
    for c in (manager_client, employee_client, anon_client):
        assert c.post(RESTORE_URL, {"confirm": "manual-20261116-101500.dump"}, format="json").status_code in (401, 403)
    assert not (online / ".restore-request").exists()
