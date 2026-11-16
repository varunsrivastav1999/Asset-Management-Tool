"""Database backups made by the `backup` service (backup/backup.sh) in a volume shared with the api.

The api never runs pg_dump itself: it lists the dump files, serves them for download, deletes them, and asks
for a new backup by dropping a request file the service picks up within seconds.
"""

import datetime
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils import timezone

NAME_RE = re.compile(r"^(auto|manual|uploaded)-\d{8}-\d{6}\.dump$")
PG_DUMP_MAGIC = b"PGDMP"  # first bytes of every pg_dump custom-format file
HEARTBEAT_MAX_AGE = 60  # seconds without a heartbeat before the service counts as offline


@dataclass(frozen=True)
class Backup:
    name: str
    kind: str
    size: int
    created_at: datetime.datetime

    def as_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "size": self.size, "created_at": self.created_at.isoformat()}


def backup_dir() -> Path:
    return Path(settings.BACKUP_DIR)


def resolve(name: str) -> Path | None:
    """Path of an existing backup, or None. Only plain backup file names are accepted (no paths)."""
    if not NAME_RE.match(name or ""):
        return None
    path = backup_dir() / name
    return path if path.is_file() else None


def list_backups() -> list[Backup]:
    folder = backup_dir()
    if not folder.is_dir():
        return []
    items = []
    for path in folder.glob("*.dump"):
        if not NAME_RE.match(path.name):
            continue
        stat = path.stat()
        created = datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.UTC)
        items.append(Backup(path.name, path.name.split("-", 1)[0], stat.st_size, created))
    return sorted(items, key=lambda b: b.created_at, reverse=True)


def pending_requests() -> int:
    folder = backup_dir() / ".requests"
    return sum(1 for _ in folder.iterdir()) if folder.is_dir() else 0


def service_online() -> bool:
    try:
        beat = int((backup_dir() / ".heartbeat").read_text().strip())
    except (OSError, ValueError):
        return False
    return time.time() - beat < HEARTBEAT_MAX_AGE


class BackupStorageError(Exception):
    """The backup folder is missing or not writable (backup service never started, or wrong BACKUP_DIR)."""


def request_backup() -> None:
    """Ask the backup service for a manual backup (picked up within ~5 seconds)."""
    folder = backup_dir() / ".requests"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{timezone.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8]}").touch()
    except OSError as exc:
        raise BackupStorageError(f"Can't write to the backup folder ({backup_dir()}). Is the backup service running?") from exc


def save_upload(upload) -> Backup:
    """Store an uploaded pg_dump file as `uploaded-<timestamp>.dump` (validated, written atomically)."""
    from rest_framework.exceptions import ValidationError

    limit_mb = settings.BACKUP_UPLOAD_MAX_MB
    if not upload.name.lower().endswith(".dump"):
        raise ValidationError({"file": "Upload a .dump file made by this app's backups (pg_dump custom format)."})
    if upload.size > limit_mb * 1024 * 1024:
        raise ValidationError({"file": f"Backup exceeds {limit_mb} MB."})
    head = upload.read(len(PG_DUMP_MAGIC))
    upload.seek(0)
    if head != PG_DUMP_MAGIC:
        raise ValidationError({"file": "That isn't a database backup (pg_dump custom format)."})
    folder = backup_dir()
    stamp = timezone.localtime()
    for _ in range(60):  # unique name even for several uploads in the same second
        name = f"uploaded-{stamp:%Y%m%d-%H%M%S}.dump"
        if not (folder / name).exists():
            break
        stamp += datetime.timedelta(seconds=1)
    target = folder / name
    partial = folder / f".{name}.part"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with partial.open("wb") as out:
            for chunk in upload.chunks():
                out.write(chunk)
        partial.replace(target)  # appears in the list only once complete
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise BackupStorageError(f"Can't write to the backup folder ({folder}).") from exc
    stat = target.stat()
    return Backup(target.name, "uploaded", stat.st_size, datetime.datetime.fromtimestamp(stat.st_mtime, tz=datetime.UTC))


def status() -> dict:
    return {
        "service_online": service_online(),
        "pending": pending_requests(),
        "schedule": settings.BACKUP_TIME,
        "keep": settings.BACKUP_KEEP,
        "backups": [b.as_dict() for b in list_backups()],
    }
