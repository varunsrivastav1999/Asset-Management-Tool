#!/bin/sh
# Container entrypoint. One image, several roles: api | worker | beat | migrate | <any command>
set -e

role="${1:-api}"
PORT="${BACKEND_PORT:-2000}"

# No secret configured? Generate one once and persist it in the private volume shared by all backend roles.
if [ -z "${DJANGO_SECRET_KEY:-}" ]; then
  key_file="${PRIVATE_MEDIA_ROOT:-/data/private}/.django_secret_key"
  if [ ! -s "$key_file" ]; then
    umask 077
    python -c "import secrets; print(secrets.token_urlsafe(64))" > "$key_file"
  fi
  DJANGO_SECRET_KEY="$(cat "$key_file")"
  export DJANGO_SECRET_KEY
fi

python manage.py wait_for_db --timeout "${DB_WAIT_TIMEOUT:-60}"

case "$role" in
  api)
    # HTTP (DRF) and WebSockets (Channels) are both served by the ASGI app on one port.
    if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
      python manage.py migrate --noinput
      python manage.py bootstrap
    fi
    if [ "${ASGI_SERVER:-gunicorn}" = "daphne" ]; then
      # Smallest footprint: one Daphne process serving HTTP + WebSockets.
      exec daphne --bind 0.0.0.0 --port "${PORT}" --proxy-headers config.asgi:application
    fi
    exec gunicorn config.asgi:application \
      --worker-class uvicorn_worker.UvicornWorker \
      --bind "0.0.0.0:${PORT}" \
      --workers "${GUNICORN_WORKERS:-2}" \
      --timeout "${GUNICORN_TIMEOUT:-60}" \
      --graceful-timeout 30 \
      --max-requests 2000 --max-requests-jitter 200 \
      --forwarded-allow-ips "*" --no-control-socket \
      --access-logfile - --error-logfile -
    ;;
  worker)
    exec celery -A config worker --loglevel "${LOG_LEVEL:-INFO}" --concurrency "${CELERY_CONCURRENCY:-1}" --max-tasks-per-child 200 --without-gossip --without-mingle
    ;;
  beat)
    exec celery -A config beat --loglevel "${LOG_LEVEL:-INFO}" --schedule /tmp/celerybeat-schedule
    ;;
  migrate)
    exec python manage.py migrate --noinput
    ;;
  *)
    exec "$@"
    ;;
esac
