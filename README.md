# Asset Management Tools

Track every company asset — IT equipment, office tools, furniture, vehicles and more — from goods-in to retirement. Issue, transfer and return assets with digital sign-off and PDF receipts, schedule maintenance, get warranty alerts, and watch it all update live. Admins can reshape the navigation, the dashboard and every table's columns for each role without touching code.

**Stack:** Vue 3 (Vite, Pinia, Tailwind v4, Chart.js, PWA) · Django 5.2 + DRF · PostgreSQL 16 · Redis 7 · Django Channels · Celery · Gunicorn + Uvicorn (ASGI) · Nginx · Docker Compose.

| Service | Port | |
|---|---|---|
| **Frontend** — Nginx serving the Vue app + reverse proxy | **2025** | public entry point |
| **Backend** — Django API + Channels (HTTP and WebSockets) | **2000** | bound to `127.0.0.1` in Docker by default |

Architecture, folder layout and the database schema are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The product name is configurable: `ORG_NAME` (backend, PDFs) and `VITE_APP_NAME` (frontend build).

## Features

| Area | What you get |
|---|---|
| Assets | CRUD for any type, nested categories with typed custom fields, serial numbers, purchase and warranty info, photos, QR codes, Code128 barcodes, printable label sheets |
| Receiving | Goods received notes (GRN): one delivery → many tagged assets, serial capture, sign-off, PDF |
| Handovers | Issue / transfer / return to employees or departments, remote or in-person digital signature, PDF receipt, expected-return tracking |
| Status | `in_stock`, `assigned`, `in_repair`, `retired`, `lost` with an enforced state machine |
| History | Immutable per-asset timeline plus a system-wide audit log (who, what, when, IP, request id) |
| Maintenance | Scheduled / in-progress / completed records; starting puts the asset in repair, completing restores it and rolls the next service date |
| Alerts | Daily Celery jobs for warranty expiry (30/7/0 days), maintenance due, overdue returns — deduplicated |
| **Custom sidebar** | Menu stored in the database (pages, external links, nested groups, dividers) with per-role visibility, icons and **colors** (label, icon, active highlight, optional gradient and glow). Admin drag-and-drop editor with icon picker, color presets, live light/dark preview and a "preview as role" panel. Changes reach every open browser instantly. |
| **Custom dashboard** | Stat, chart and table widgets stored in the database with size, position and per-role visibility; admin-only editor; organisation-wide data can never be shown to employees |
| **Configurable tables** | Every list page (Assets, Receiving, Handovers, Maintenance, People, Departments, Locations, Vendors) renders from a column config: built-ins such as S.No, Item, Received, Status and Assigned To can be renamed, hidden, reordered and role-restricted; admins add custom columns (text, number, date, yes/no, select, user, file) whose values live in each record's `custom_data` and are edited inline. Search, sort, filters and CSV/Excel export follow the config; every user can save their own column visibility. |
| Realtime | WebSocket notifications, live dashboard data, live sidebar / dashboard-layout / column changes |
| Access | Admin, Manager, Employee roles enforced on every endpoint; JWT with rotating HttpOnly refresh cookie |
| Data | Search, filters, CSV/Excel export, validated all-or-nothing CSV/Excel asset import with dry run |
| UI | Dark/light/system themes, glassmorphism, animations, responsive with a mobile bottom bar, installable PWA, camera scanner |

### Roles

| | Admin | Manager | Employee |
|---|---|---|---|
| Sidebar, dashboard and table-column configuration; audit log | full | — | — |
| Users, departments | full | read | — |
| Assets, catalog, receiving, handovers, maintenance, import/export, custom column values | full | full | read own assets |
| Personal column visibility, sign handovers addressed to them, notifications, profile | ✔ | ✔ | ✔ |
| Django admin (`/admin/`) | superusers only | — | — |

Everything day-to-day (users, departments, categories and custom fields, locations, vendors, sidebar, dashboard, table columns) has an in-app screen; the Django admin is kept as a break-glass tool and has every model registered.

### Configurable tables in practice

- Open any list page → **Columns**. Everyone can tick columns on or off for their own view (stored per user; required columns stay on). **Reset my view** restores the defaults.
- Admins also drag to reorder for everyone, rename inline, expand a column to change default visibility, required/searchable/sortable flags, width and visible roles, add a column (name + type, plus options for select), delete custom columns, or **Reset for everyone**.
- Custom column values are edited by clicking a cell (managers and admins). They're stored in the record's `custom_data` JSONB, so adding a column never needs a migration. A custom column whose key matches an asset category field (for example `ram_gb`) shows that field's value.
- Columns are attached to a **sidebar page**, so two menu entries for the same table (say `/assets` and `/assets?status=in_repair` "Repairs") can have different columns.
- The API returns the column config with the rows (`?with_columns=1&table_item=<id>`); `?search=`, `?ordering=<key>` and `?cf.<key>=` follow the config, and `…/export-table/?file_format=csv|xlsx` exports exactly the columns the user sees, in order, with their labels.

## Quick start (Docker)

Requirements: Docker 24+ with Compose v2.

```bash
cp .env.example .env
```

Edit `.env`: set `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` (the defaults are plain-HTTP friendly for a local trial).

```bash
docker compose up -d --build
```

```bash
docker compose exec api python manage.py createsuperuser
```

Open **http://localhost:2025**. To load demo data (departments, categories with custom fields, ~60 assets, and accounts `admin@`, `manager@`, `employee@example.com` with password `Demo@12345`):

```bash
docker compose exec api python manage.py seed_demo
```

Services: `nginx` (:2025) → `api` (:2000, Gunicorn + Uvicorn workers running the ASGI app, so DRF and Channels share one port; applies migrations on start), `worker` + `beat` (Celery), `postgres`, `redis`. `docker compose ps` shows health.

| URL | |
|---|---|
| `http://localhost:2025/` | the app |
| `/api/docs/` | Swagger UI (OpenAPI schema at `/api/schema/`) |
| `/api/health/`, `/api/health/ready/` | liveness, readiness (DB + cache) |
| `/admin/` | Django admin — superusers only, private networks only (see below) |

Default sidebar items, dashboard widgets and table columns are created by migrations (columns are also created on demand for new table pages); admins can restore them any time with **Reset** in the settings screens or the Columns panel.

## Production checklist

1. **HTTPS:** put `fullchain.pem` and `privkey.pem` in `nginx/certs/`, replace `nginx/conf.d/default.conf` with `nginx/https.conf.example`, rebuild `nginx`. The app is then served over TLS on 2025; front it with a 443 load balancer or port mapping for a bare domain. Set `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SECURE_COOKIES` and `JWT_COOKIE_SECURE` to `true`.
2. Set `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and `FRONTEND_URL` to your real origin (QR codes encode `FRONTEND_URL/a/<tag>`).
3. Use a long random `DJANGO_SECRET_KEY` (the app refuses to start with a weak one) and a strong `POSTGRES_PASSWORD`.
4. **Django admin:** only active superusers can sign in. Nginx additionally allows `/admin/` only from loopback/private ranges — edit `nginx/snippets/admin-access.conf` for your office/VPN, and optionally add basic auth (`nginx/admin-auth/README.md`). If you change `DJANGO_ADMIN_URL`, update the `location /admin/` block too.
5. Keep `BACKEND_BIND=127.0.0.1` so the API is only reachable through nginx (headers, rate limits, admin allowlist).
6. Back up the `pgdata`, `media` and `private_media` volumes. `private_media` holds signatures and is never served by nginx.
7. Ship logs: everything logs JSON to stdout (`LOG_FORMAT=json`); each request carries an `X-Request-ID` that also appears in audit entries.

Upgrading: `docker compose up -d --build` — the `api` container applies migrations before starting (`RUN_MIGRATIONS=false` to disable and run `docker compose run --rm api migrate` yourself).

## Local development

Requirements: Python 3.12, Node 24+, and Postgres + Redis (run them from Compose):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis
```

Backend (http://localhost:2000):

```bash
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements/base.txt -r requirements/dev.txt
```

Create `backend/.env` with at least `DJANGO_DEBUG=true`, `DATABASE_URL=postgres://asset:<password>@localhost:5432/asset`, `REDIS_URL=redis://localhost:6379` and `CELERY_TASK_ALWAYS_EAGER=true` (runs tasks inline so you don't need a worker), then:

```bash
cd backend && .venv/bin/python manage.py migrate && .venv/bin/python manage.py seed_demo && .venv/bin/python manage.py runserver 0.0.0.0:2000
```

`runserver` uses Daphne, so WebSockets work in development too.

Frontend (http://localhost:2025, proxies `/api`, `/media` and `/ws` to `localhost:2000`):

```bash
cd frontend && npm install && npm run dev
```

Alternatively run everything in Docker with the API published on all interfaces and debug logs:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Tests and quality

```bash
cd backend && .venv/bin/pytest --cov
```

```bash
cd backend && .venv/bin/ruff check apps config tests && .venv/bin/ruff format --check apps config tests
```

```bash
cd frontend && npm run lint && npm test && npm run build
```

Backend tests need Postgres (`DATABASE_URL`, default `postgres://localhost/asset_test`). They cover auth and cookie rotation, RBAC on every resource, the asset state machine, custom fields, receiving, all handover types and sign-off rules, import/export (incl. CSV-injection protection), maintenance, alert deduplication, the dashboard cache, the WebSocket consumer, the sidebar (role filtering, validation, colors, reorder and cycle protection), dashboard widget permissions and data-exposure rules, table columns (admin-only management, built-in protections, custom values, config-driven search/sort/filter/export, role-restricted columns, per-user visibility), realtime config broadcasts, and the superuser-only Django admin. Frontend tests cover the API client, realtime client, stores, sidebar rendering and colors, dashboard widgets, and table cells and columns.

CI (`.github/workflows/ci.yml`) runs lint, a migration drift check, `check --deploy`, backend tests with an 80% coverage gate against Postgres, frontend lint/tests/build, and builds both Docker images.

## Security notes

- Every API endpoint declares a role-based permission; sidebar, dashboard and column configuration are admin-only, and all their changes (plus custom value edits and personal column choices) are audited.
- Access token lives only in memory; the refresh token is an `HttpOnly; Secure; SameSite=Strict` cookie scoped to `/api/auth/`, rotated on every use and blacklisted on logout.
- WebSockets authenticate with a first message — tokens never appear in URLs or proxy logs — and only accept same-host origins.
- Sidebar links are restricted to in-app paths or absolute http(s) URLs (no `javascript:`); colors must be hex values and are re-validated in the browser before use; external links and file cells open with `noopener`.
- Custom column values are type-checked server-side (file cells accept only http(s) or `/media/` links); columns restricted to certain roles are hidden from, and not searchable by, other roles.
- Login is rate limited in nginx and DRF; failed logins are audited.
- Strict CSP for the SPA, `nosniff`, `DENY` framing, restricted `Permissions-Policy` (camera allowed for the scanner), HSTS on HTTPS.
- Uploads are size-limited and verified with Pillow; signatures must be non-empty images; all exports neutralise spreadsheet formulas.
- Containers run as non-root with `no-new-privileges`.

## Project layout

```
backend/    Django project (config/ settings, apps/ domain apps incl. navigation + dashboard, tests/)
frontend/   Vue SPA (src/api, stores, views, components) + Dockerfile for the nginx image
nginx/      nginx.conf, server blocks, shared snippets (security headers, admin allowlist), certs/, admin-auth/
docs/       ARCHITECTURE.md
```
