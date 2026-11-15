# Asset Management Tools

Track every company asset — IT equipment, office tools, furniture, vehicles and more — from goods-in to retirement. Issue, transfer and return assets with digital sign-off and PDF receipts, schedule maintenance, get warranty alerts, and watch it all update live. Admins can reshape the navigation, the dashboard, every table's name and columns, and the email/SMS reminder rules for each role without touching code.

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
| **Editable tables** | Rename any table (plural name, singular name used in buttons such as "Add Laptop", icon, description) and the menu, page titles, breadcrumbs, buttons and empty states all follow. Create your own tables with typed columns, served at `/t/<slug>`. A table that still holds rows can't be deleted: archive its rows or move them to another table first. Names are unique (case-insensitive) and every change is audited. |
| **Bulk actions** | Every table has row checkboxes, "select all N results" across pages and a bulk bar: **Delete** (one atomic request; rows that can't be removed are skipped with a reason, for example an asset that is still assigned), **Change status**, and **Export CSV** of the selected, filtered or all rows. Admin and Manager only. |
| **Email & SMS reminders** | Rules per section with triggers (warranty expiry, maintenance due, overdue return, handover awaiting signature, new goods receipt, low stock, status change, custom date column, manual), recipients (assignee, department head, roles, specific users or addresses), schedules (daily, weekly, once or manual) and channels (email, SMS, in-app). Templates with `{{variable}}` chips and live preview. Bills, receipt PDFs and exports are attached; files over 10 MB become signed links that expire, and SMS always gets a link. Delivery log with filters and CSV export. |
| Realtime | WebSocket notifications, live dashboard data, live sidebar / dashboard-layout / column changes |
| Access | Admin, Manager, Employee roles enforced on every endpoint; JWT with rotating HttpOnly refresh cookie |
| Data | Search, filters, CSV/Excel export, validated all-or-nothing CSV/Excel asset import with dry run |
| UI | Green theme defined once in CSS variables (every text/background pair meets WCAG AA), dark/light/system themes, glassmorphism, one shared confirm dialog for every delete (shows the count, traps focus, closes on Esc, shows a spinner while working, and always sits above open modals), animations, responsive with a mobile bottom bar, installable PWA, camera scanner |

### Roles

| | Admin | Manager | Employee |
|---|---|---|---|
| Sidebar, dashboard, table names and columns, create/delete tables; audit log | full | — | — |
| Reminder channel settings (email/SMS on or off, provider, rate limits, daily cap) | full | — | — |
| Reminder rules and templates | all sections | sections they can see | — |
| Bulk delete, bulk status change, CSV export of selections | ✔ | ✔ | — |
| Users, departments | full | read | — |
| Assets, catalog, receiving, handovers, maintenance, import/export, custom column values | full | full | read own assets |
| Personal column visibility, own reminder preferences (opt out per channel or section, verify phone), sign handovers addressed to them, notifications, profile | ✔ | ✔ | ✔ |
| Django admin (`/admin/`) | superusers only | — | — |

Everything day-to-day (users, departments, categories and custom fields, locations, vendors, sidebar, dashboard, table columns) has an in-app screen; the Django admin is kept as a break-glass tool and has every model registered.

### Configurable tables in practice

- Open any list page → **Columns**. Everyone can tick columns on or off for their own view (stored per user; required columns stay on). **Reset my view** restores the defaults.
- Admins also drag to reorder for everyone, rename inline, expand a column to change default visibility, required/searchable/sortable flags, width and visible roles, add a column (name + type, plus options for select), delete custom columns, or **Reset for everyone**.
- Custom column values are edited by clicking a cell (managers and admins). They're stored in the record's `custom_data` JSONB, so adding a column never needs a migration. A custom column whose key matches an asset category field (for example `ram_gb`) shows that field's value.
- Columns are attached to a **sidebar page**, so two menu entries for the same table (say `/assets` and `/assets?status=in_repair` "Repairs") can have different columns.
- The API returns the column config with the rows (`?with_columns=1&table_item=<id>`); `?search=`, `?ordering=<key>` and `?cf.<key>=` follow the config, and `…/export-table/?file_format=csv|xlsx` exports exactly the columns the user sees, in order, with their labels.

### Reminders in practice

- Open **Reminders** in the menu, or the bell button in any section's page header, which opens the rules already filtered to that section.
- **Rules** tab: pick a trigger and its settings (for example "30 and 7 days before warranty expiry"), recipients, channels, schedule and template, then **Test** to send one sample to yourself or **Send now**. Three example rules are seeded, all switched off.
- **Templates** tab: subject, email body and a 160-character SMS text. Click a variable chip to insert it; the preview fills in real or sample data.
- **Logs** tab: every message with its status (queued, sent, failed or skipped, and why), filterable and exportable as CSV.
- **Channels** (admin): turn email, SMS and in-app on or off, choose the SMS provider, sender ID, per-minute rate limits and daily cap. SMTP and SMS credentials come only from environment variables and are never returned by the API.
- Delivery: Celery beat scans the rules every 5 minutes. Each message has a unique dedupe key, so nobody gets the same reminder twice. Failures retry with exponential backoff (up to 5 attempts), and admins are alerted when a message finally fails. Opt-outs and quiet hours are always respected, and SMS only goes to verified phone numbers.
- SMS providers: `console` (writes to the logs, the default), `twilio` (`SMS_API_KEY=ACCOUNT_SID:AUTH_TOKEN`) and `msg91`.

API: `/api/reminders/rules/` (plus `{id}/test/`, `{id}/send-now/`), `/api/reminders/templates/` (plus `preview/`, `variables/`), `/api/reminders/logs/` (plus `export/`, `{id}/retry/`), `/api/reminders/channels/`, `/api/reminders/preferences/`.

### Tables and bulk actions in practice

- **Settings → Tables** lists every table with its row count. **New table** asks for a name, the singular form, an icon, the menu group, the roles that can see it and the first columns. **Delete** first checks for rows and, if any exist, sends you to the table to archive or move them.
- On any list page, tick rows (or the header box, then **Select all N**) and use the bulk bar. The **Export** menu offers all rows, filtered rows or the selected rows. CSV files carry a UTF-8 BOM so Excel opens them correctly, and cells that look like formulas are neutralised.
- API: `POST /api/<resource>/bulk-delete/` with `{"ids": [...]}` or `{"all": true}` plus the current filters as query parameters returns `{deleted, skipped: [{id, label, reason}]}`; `GET /api/<resource>/export-table/?file_format=csv&scope=all|filtered|selected&ids=…`; `/api/table-definitions/` (plus `{id}/delete-check/`); `/api/records/` (plus `bulk-archive/`, `bulk-move/`) for custom tables.

## Quick start (Docker)

Requirements: Docker 24+ with Compose v2.

One command, no `.env` and no manual steps:

```bash
docker compose up -d --build
```

On first start the stack sets itself up:
- generates a strong `DJANGO_SECRET_KEY` and stores it in the `private_media` volume;
- applies migrations and seeds the default menu, table definitions and columns, dashboard widgets and the (disabled) reminder rules;
- on a fresh database only, creates the first admin, **admin@gmail.com** with password **admin** (or `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`);
- starts the backup service, which takes a first database backup straight away.

Open **https://localhost:2025** and sign in as `admin@gmail.com` / `admin`. Until you change that password, every page shows a reminder with a link to do it, because anyone on your network could otherwise sign in with it. Restarting or rebuilding never changes existing data, accounts or passwords. To customise anything, copy `.env.example` to `.env` (every setting is documented there).

To load demo data (departments, categories with custom fields, ~60 assets, and accounts `admin@`, `manager@`, `employee@example.com` with password `Demo@12345`):

```bash
docker compose exec api python manage.py seed_demo
```

Services: `nginx` (:2025) → `api` (:2000, Gunicorn + Uvicorn workers running the ASGI app, so DRF and Channels share one port), `worker` + `beat` (Celery), `postgres`, `redis`. Every service has a healthcheck and starts only after the services it depends on are healthy; `docker compose ps` shows the state.

The stack is tuned for a small server: memory limits (Postgres 320 MB, Redis 96 MB, api 512 MB, worker 384 MB, beat 192 MB, nginx 64 MB), slim images, pre-compressed brotli and gzip assets, and `GUNICORN_WORKERS` / `CELERY_CONCURRENCY` to scale up. On a very small box, `ASGI_SERVER=daphne` serves everything from a single process.

| URL | |
|---|---|
| `https://localhost:2025/` | the app (plain `http://` on the same port redirects to HTTPS) |
| `/api/docs/` | Swagger UI (OpenAPI schema at `/api/schema/`) |
| `/api/health/`, `/api/health/ready/` | liveness, readiness (DB + cache) |
| `/admin/` | Django admin — superusers only, private networks only (see below) |

Default sidebar items, dashboard widgets and table columns are created by migrations (columns are also created on demand for new table pages); admins can restore them any time with **Reset** in the settings screens or the Columns panel.

### Backups

- The `backup` service runs Postgres' own `pg_dump` (same version as the database). It backs up the database every day at `BACKUP_TIME` (default 02:00, in `TIME_ZONE`), keeps the newest `BACKUP_KEEP` daily backups (default 7), and takes one immediately on first start.
- **Settings → Backups** (admins) shows the service status, schedule and every backup. You can **Back up now**, **download** a backup (keep copies off this machine) and delete old ones. Every action is recorded in the audit log.
- Backups are stored in the `backups` Docker volume as `auto-YYYYMMDD-HHMMSS.dump` / `manual-….dump` (compressed `pg_dump` custom format). List them from the terminal:

```bash
docker compose exec backup /scripts/backup.sh list
```

- **Restore** replaces all current data with the backup. Stop the app first, restore, then start it again:

```bash
docker compose stop api worker beat
```

```bash
docker compose run --rm backup restore manual-20261116-101500.dump
```

```bash
docker compose start api worker beat
```

- To restore a downloaded file, copy it into the volume first, then run the same `restore` command with its name:

```bash
docker compose cp ./manual-20261116-101500.dump backup:/backups/
```

- Uploaded files (photos, signatures, invoices) live in the `media` and `private_media` volumes; back those up with your usual volume or host backup.

### Using it from phones and other devices

- Every device on the same network can open **https://<this machine's IP>:2025**. No IP needs configuring: any private-network address (192.168.x.x, 10.x.x.x, `*.local` …) is accepted automatically, so it keeps working when the IP changes. QR codes, PDFs and email links use the address the app was opened on (set `FRONTEND_URL` to pin one).
- **Camera / QR scanner:** browsers only allow the camera on HTTPS pages (or `localhost`), which is why nginx serves HTTPS by default. On first visit each device shows a certificate warning for the self-signed certificate: tap **Advanced → Proceed** (Chrome) or **Show Details → visit this website** (Safari) once, then allow the camera.
- **No warning at all:** create a locally trusted certificate with [mkcert](https://github.com/FiloSottile/mkcert) (`mkcert -install`, then `mkcert -cert-file nginx/certs/fullchain.pem -key-file nginx/certs/privkey.pem localhost 127.0.0.1 <your LAN IP>`), restart nginx, and install mkcert's root CA on each phone (`mkcert -CAROOT` shows where it is). Offline-install (PWA) also needs a trusted certificate.
- If other devices can't connect, allow incoming connections for Docker in the computer's firewall, and make sure they're on the same Wi-Fi/LAN.

## Production checklist

1. **HTTPS:** put a real `fullchain.pem` and `privkey.pem` in `nginx/certs/` and restart `nginx`; it picks them up automatically (with HSTS) instead of the self-signed certificate. Front port 2025 with a 443 load balancer or port mapping for a bare domain. Set `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SECURE_COOKIES` and `JWT_COOKIE_SECURE` to `true`, and `ALLOW_PRIVATE_NETWORK_HOSTS=false` if the server must only answer its domain.
2. Set `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` and `FRONTEND_URL` to your real origin (QR codes encode `FRONTEND_URL/a/<tag>`).
3. Set a strong `POSTGRES_PASSWORD` and `ADMIN_PASSWORD`. `DJANGO_SECRET_KEY` is generated automatically if unset; if you set it yourself it must be long and random (the app refuses to start with a weak one).
4. **Email/SMS:** set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `DEFAULT_FROM_EMAIL` and, for SMS, `SMS_PROVIDER`, `SMS_API_KEY`, `SMS_SENDER_ID`. Without `SMTP_HOST`, emails are written to the logs.
5. **Django admin:** only active superusers can sign in. Nginx additionally allows `/admin/` only from loopback/private ranges — edit `nginx/snippets/admin-access.conf` for your office/VPN, and optionally add basic auth (`nginx/admin-auth/README.md`). If you change `DJANGO_ADMIN_URL`, update the `location /admin/` block too.
6. Keep `BACKEND_BIND=127.0.0.1` so the API is only reachable through nginx (headers, rate limits, admin allowlist).
7. Database backups run automatically (see **Backups**): download them regularly, and also back up the `media` and `private_media` volumes. `private_media` holds signatures and invoices and is never served by nginx.
8. Ship logs: everything logs JSON to stdout (`LOG_FORMAT=json`); each request carries an `X-Request-ID` that also appears in audit entries.

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

Alternatively run everything in Docker with the API published on all interfaces, debug logs and **MailHog** catching every email (read them at http://localhost:8025). Add `mailhog` to the infrastructure-only command above to use it with a host-run backend (`SMTP_HOST=localhost`, `SMTP_PORT=1025`, `SMTP_USE_TLS=false`).


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

Backend tests need Postgres (`DATABASE_URL`, default `postgres://localhost/asset_test`). They cover auth and cookie rotation, RBAC on every resource, the asset state machine, custom fields, receiving, all handover types and sign-off rules, import/export (incl. CSV-injection protection), maintenance, alert deduplication, the dashboard cache, the WebSocket consumer, the sidebar (role filtering, validation, colors, reorder and cycle protection), dashboard widget permissions and data-exposure rules, table columns (admin-only management, built-in protections, custom values, config-driven search/sort/filter/export, role-restricted columns, per-user visibility), realtime config broadcasts, the superuser-only Django admin, table definitions (rename, create, unique names, delete blocked while rows exist, archive/move), bulk delete/status/export on every resource (skip reasons, `all` with filters, role checks), CSV formula escaping, the first-start bootstrap, and reminders (scheduling, every trigger, recipients, opt-outs and verified phones, dedupe, retries with backoff, rate limits and daily cap, attachments and signed links, template rendering, permissions per role, secrets never in responses, a mocked SMS provider). Frontend tests cover the API client, realtime client, stores, sidebar rendering and colors, dashboard widgets, table cells and columns, the confirm dialog (stacking above modals, Esc, focus trap, loading) and bulk actions.

CI (`.github/workflows/ci.yml`) runs lint, a migration drift check, `check --deploy`, backend tests with an 80% coverage gate against Postgres, frontend lint/tests/build, and builds both Docker images.

## Security notes

- Every API endpoint declares a role-based permission; sidebar, dashboard and column configuration are admin-only, and all their changes (plus custom value edits and personal column choices) are audited.
- Access token lives only in memory; the refresh token is an `HttpOnly; Secure; SameSite=Strict` cookie scoped to `/api/auth/`, rotated on every use and blacklisted on logout.
- WebSockets authenticate with a first message — tokens never appear in URLs or proxy logs — and only accept same-host origins.
- Sidebar links are restricted to in-app paths or absolute http(s) URLs (no `javascript:`); colors must be hex values and are re-validated in the browser before use; external links and file cells open with `noopener`.
- Custom column values are type-checked server-side (file cells accept only http(s) or `/media/` links); columns restricted to certain roles are hidden from, and not searchable by, other roles.
- Login is rate limited in nginx and DRF; failed logins are audited.
- Strict CSP for the SPA, `nosniff`, `DENY` framing, restricted `Permissions-Policy` (camera allowed for the scanner), HSTS on HTTPS.
- Email/SMS credentials exist only in environment variables; the channel settings API never returns them. Attachment links are signed and expire (`REMINDER_LINK_HOURS`), and attached files are read from private storage.
- Bills/invoices and signatures live in private storage and are only served through permission-checked endpoints.
- Uploads are size-limited and verified with Pillow; signatures must be non-empty images; all exports neutralise spreadsheet formulas.
- Containers run as non-root with `no-new-privileges`.

## Project layout

```
backend/    Django project (config/ settings, apps/ domain apps incl. navigation, dashboard and reminders, tests/)
frontend/   Vue SPA (src/api, stores, views, components) + Dockerfile for the nginx image
nginx/      nginx.conf, server blocks, shared snippets (security headers, admin allowlist), certs/, admin-auth/
docs/       ARCHITECTURE.md
```
