#!/bin/sh
# Database backups for the Docker stack (runs in the postgres:16-alpine image, so pg_dump matches the server).
#
#   (default)            run forever: a backup at first start if none exists, a daily "auto" backup at
#                        BACKUP_TIME (keeping the newest BACKUP_KEEP), "manual" backups requested from
#                        the app (Settings -> Backups, a file in /backups/.requests) and restores requested
#                        from the app (/backups/.restore-request holding the backup's file name).
#   now                  take one manual backup and exit
#   restore <file>       replace the database with a backup (the app may keep running; see README)
#   list                 list backups
#
# Restores never touch the live database until the backup has loaded completely: it is restored into a
# scratch database which is then swapped in by renaming (one transaction), and a "safety" backup of the
# current data is taken first. If anything fails, the current data stays as it was.
#
# Files: /backups/{auto,manual,uploaded,safety}-YYYYMMDD-HHMMSS.dump  (pg_dump custom format, compressed)
set -eu

DIR=/backups
REQ="$DIR/.requests"
RESTORE_REQ="$DIR/.restore-request"
RESTORE_STATE="$DIR/.restore-state"
SAFETY_KEEP=3
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
  # Keep the newest $2 backups of kind $1; manual and uploaded ones stay until deleted in the app.
  ls -1t "$DIR/$1"-*.dump 2>/dev/null | tail -n +"$(($2 + 1))" | while read -r old; do
    rm -f "$old" && log "removed old backup: $(basename "$old")"
  done
}

sql() { psql -d postgres -v ON_ERROR_STOP=1 -q -X "$@"; }

restore_db() {
  # Load backup file $1 into a scratch database, then swap it in for $PGDATABASE.
  file="$1"; db="$PGDATABASE"; tmp="${db}__restore"; old="${db}__old"
  sql -c "DROP DATABASE IF EXISTS \"$tmp\" WITH (FORCE)" -c "CREATE DATABASE \"$tmp\"" || return 1
  if ! pg_restore --no-owner --no-privileges --exit-on-error --dbname="$tmp" "$file" 2>"$DIR/.restore-log"; then
    log "restore failed while loading $(basename "$file"): $(tail -n 1 "$DIR/.restore-log")" >&2
    sql -c "DROP DATABASE IF EXISTS \"$tmp\" WITH (FORCE)" || true
    return 1
  fi
  sql -c "DROP DATABASE IF EXISTS \"$old\" WITH (FORCE)" || return 1
  # Keep the app out for the instant of the swap: no new connections, end the open ones, rename both.
  for attempt in 1 2 3 4 5; do
    if sql -o /dev/null <<SQL
ALTER DATABASE "$db" ALLOW_CONNECTIONS false;
SELECT pg_terminate_backend(pid, 5000) FROM pg_stat_activity WHERE datname = '$db' AND pid <> pg_backend_pid();
BEGIN;
ALTER DATABASE "$db" RENAME TO "$old";
ALTER DATABASE "$tmp" RENAME TO "$db";
COMMIT;
SQL
    then
      sql -c "DROP DATABASE IF EXISTS \"$old\" WITH (FORCE)" || log "could not drop $old (harmless)" >&2
      return 0
    fi
    sql -c "ALTER DATABASE \"$db\" ALLOW_CONNECTIONS true" || true
    log "swap attempt $attempt failed; retrying" >&2
    sleep 1
  done
  sql -c "DROP DATABASE IF EXISTS \"$tmp\" WITH (FORCE)" || true
  return 1
}

state() {
  # $1 state, $2 backup name, $3 message: read by the app (Settings -> Backups) to show progress.
  msg="$(printf '%s' "${3:-}" | tr -d '"\\' | tr '\n\r\t' '   ' | cut -c1-300)"
  printf '{"state": "%s", "name": "%s", "message": "%s", "at": %s, "id": "%s"}\n' \
    "$1" "$2" "$msg" "$(date +%s)" "$RUN_ID" > "$RESTORE_STATE.part"
  chown "$APP_UID" "$RESTORE_STATE.part" 2>/dev/null || true
  mv "$RESTORE_STATE.part" "$RESTORE_STATE"
}

handle_restore() {
  name="$(basename "$(head -n 1 "$RESTORE_REQ" | tr -d '\r\n ')")"
  rm -f "$RESTORE_REQ"
  RUN_ID="$(date +%s)-$$"
  case "$name" in
    auto-*.dump|manual-*.dump|uploaded-*.dump|safety-*.dump) ;;
    *) state failed "$name" "Not a backup file name."; return ;;
  esac
  [ -f "$DIR/$name" ] || { state failed "$name" "The backup file no longer exists."; return; }
  state running "$name" "Saving the current data first"
  log "restore of $name requested from the app; taking a safety backup first"
  if ! dump safety; then
    state failed "$name" "Could not back up the current data, so nothing was changed."
    return
  fi
  prune safety "$SAFETY_KEEP"
  state running "$name" "Loading the backup"
  if restore_db "$DIR/$name"; then
    log "restore finished: $name is now the live database"
    state done "$name" "Restored"
  else
    state failed "$name" "Restore failed, so your data was not changed. $(tail -n 1 "$DIR/.restore-log" 2>/dev/null)"
  fi
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
    restore_db "$file" || { echo "Restore failed; the database was not changed." >&2; exit 1; }
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
      if [ -f "$RESTORE_REQ" ]; then
        handle_restore || true
        date +%s > "$DIR/.heartbeat"
      fi
      today="$(date +%Y%m%d)"
      if [ "$(date +%H%M)" -ge "$AT" ] && ! ls "$DIR"/auto-"$today"-*.dump >/dev/null 2>&1; then
        dump auto && prune auto "$KEEP" || true
      fi
      sleep 5
    done
    ;;
  *)
    echo "usage: backup.sh [run|now|list|restore <file>]" >&2
    exit 2
    ;;
esac
