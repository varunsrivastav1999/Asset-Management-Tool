# syntax=docker/dockerfile:1.7

# ---- builder: compile wheels once --------------------------------------------
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements/base.txt requirements/base.txt
RUN pip wheel --wheel-dir /wheels -r requirements/base.txt

# ---- runtime -----------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    STATIC_ROOT=/app/staticfiles \
    MEDIA_ROOT=/data/media \
    PRIVATE_MEDIA_ROOT=/data/private \
    BACKEND_PORT=2000

RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --home /app --shell /usr/sbin/nologin app

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/* && rm -rf /wheels

WORKDIR /app
COPY --chown=app:app . .
RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /data/media /data/private /app/staticfiles \
    && chown -R app:app /data /app/staticfiles \
    && DJANGO_SECRET_KEY=build-only-placeholder-key-not-used-at-runtime-0000000000 \
       python manage.py collectstatic --noinput -v0

USER app
EXPOSE 2000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health/' % os.environ.get('BACKEND_PORT','2000'), timeout=4)" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["api"]
