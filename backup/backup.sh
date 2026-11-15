#!/bin/sh
# Database backups for the Docker stack (runs in the postgres:16-alpine image, so pg_dump matches the server).
#
#   (default)            run forever: a backup at first start if none exists, a daily "auto" backup at
#                        BACKUP_TIME (keeping the newest BACKUP_KEEP), and "manual" backups requested from
#                        the app (Settings -> Backups), which drops a file into /backups/.requests.
#   now                  take one manual backup and exit
#   restore <file>       replace the database with a backup (stop api/worker/beat first; see README)
#   list                 list backups
#
# Files: /backups/{auto,manual}-YYYYMMDD-HHMMSS.dump  (pg_dump custom format, compressed)
set -eu

DIR=/backups
REQ="$DIR/.requests"
KEEP="${BACKUP_KEEP:-7}"
AT="$(echo "${BACKUP_TIME:-02:00}" | tr -d ':')"
APP_UID="${APP_UID:-1000}"

log() { echo "[backup] $(date '+%Y-%m-%d %H:%M:%S %Z') $*"; }

prepare() {
  mkdir -p "$REQ"
  # The api container (uid $APP_UID) lists, downloads and deletes backups and drops requests here.
  chown "$APP_UID" "$DIR" "$REQ"
  chmod 0770 "$DIR" "$REQ"
}

dump() {
  kind="$1"
  file="$DIR/$kind-$(date +%Y%m%d-%H%M%S).dump"
  if pg_dump --format=custom --no-owner --no-privileges --file="$file.part"; then
    mv "$file.part" "$file"
    chown "$APP_UID" "$file"
    chmod 0640 "$file"
    log "backup written: $(basename "$file") ($(du -h "$file" | cut -f1))"
  else
    rm -f "$file.part"
    log "BACKUP FAILED ($kind)" >&2
    return 1
  fi
}

prune() {
  # Keep the newest $KEEP automatic backups; manual ones stay until deleted in the app.
  ls -1t "$DIR"/auto-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
    rm -f "$old" && log "removed old backup: $(basename "$old")"
  done
}

has_backups() { ls "$DIR"/*.dump >/dev/null 2>&1; }

wait_for_db() {
  until pg_isready -q; do sleep 2; done
}

case "${1:-run}" in
  now)
    prepare; wait_for_db; dump manual
    ;;
  list)
    ls -lh "$DIR"/*.dump 2>/dev/null || echo "No backups yet."
    ;;
  restore)
    name="${2:-}"
    [ -n "$name" ] || { echo "usage: restore <file name from 'list'>" >&2; exit 2; }
    file="$DIR/$(basename "$name")"
    [ -f "$file" ] || { echo "No such backup: $name" >&2; exit 1; }
    wait_for_db
    log "restoring $(basename "$file") into $PGDATABASE (existing data is replaced)"
    pg_restore --clean --if-exists --no-owner --no-privileges --single-transaction --dbname="$PGDATABASE" "$file"
    log "restore finished"
    ;;
  run)
    prepare
    wait_for_db
    log "daily backup at ${BACKUP_TIME:-02:00} ($(date +%Z)), keeping $KEEP; manual backups on request"
    has_backups || dump auto || true
    while true; do
      date +%s > "$DIR/.heartbeat"
      for request in "$REQ"/*; do
        [ -e "$request" ] || continue
        rm -f "$request"
        dump manual || true
      done
      today="$(date +%Y%m%d)"
      if [ "$(date +%H%M)" -ge "$AT" ] && ! ls "$DIR"/auto-"$today"-*.dump >/dev/null 2>&1; then
        dump auto && prune || true
      fi
      sleep 5
    done
    ;;
  *)
    echo "usage: backup.sh [run|now|list|restore <file>]" >&2
    exit 2
    ;;
esac
