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
