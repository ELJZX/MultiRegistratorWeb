# AGENTS.md

Django 6.1 + Modbus TCP data logger. Django project package: `multiregistrator_web`; the only local app is `devices`. UI text, admin labels, command help and `README.md` are Russian — keep new user-facing strings Russian. `README.md` is the detailed reference for env vars, API, storage modes and the demo flow. CI uses Python 3.12 and Node 20, while the Docker image uses Python 3.15 — don't assume those versions match.

## Reliability rules

This service collects meter readings; silent data loss is worse than a visible outage.

- Keep polling single-instance and single-writer. Never add polling to the web/Gunicorn process or run more than one poller against the same devices; duplicate polls create duplicate measurements and unstable connections.
- A failed read or storage write must be visible: log the device id/host, persist the error/status, and never swallow exceptions. Distinguish device-offline errors from storage errors.
- Use timezone-aware UTC for DB timestamps; convert to local time only at the CSV/UI boundary. No `datetime.now()` or naive datetimes in polling/storage code.
- Preserve read resilience: one connection per device, bounded timeouts/retries, reconnect on failure, and a bad channel/block must not discard values from healthy blocks.
- Storage changes must be atomic and backward compatible. Keep CSV appends thread-safe; when testing `ARCHIVE_STORAGE=files`, reset the cached `devices.storage._writer`/`_reader` handles.
- Migrations must be backward compatible and run once, before new app containers start. Back up the DB before destructive or long migrations; never rely on two services racing to run `migrate`.
- Every behavior change needs a regression test; the Django and JS suites must pass before merge. Socket tests must bind to localhost port 0 and must not depend on external devices.
- Keep API response shapes and `ARCHIVE_STORAGE` semantics backward compatible. `/api/*` remains public for integrations; do not add auth or trailing slashes without an explicit breaking-change decision.
- Production deployments use immutable versioned images/tags, never `latest`, and must be health-gated with a tested rollback to the previous image.

## Commands

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver        # web UI/API only; it never polls devices
python manage.py poll_devices     # separate long-running poller (--once for one cycle)
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test             # Django suite; simulator tests use real localhost sockets
python manage.py test devices.tests.test_modbus.DecodeTests.test_uint16
npm run test:js                   # Node 20 in CI; no npm install or frontend build
```

- CI (`.github/workflows/ci.yml`) runs `check`, `check_version.py --current`, the migration-drift check, `manage.py test -v 2` on SQLite and PostgreSQL, `npm run test:js`, and a Docker Compose smoke test. There is no lint/format/typecheck config; use the commands above as the verification gate.
- Runtime dependencies are exact-pinned in `requirements.txt`; Dependabot updates pip, npm, Docker and GitHub Actions weekly.
- Local default DB is SQLite; setting `DB_HOST` switches to PostgreSQL. Docker uses PostgreSQL 16.
- Docker: `docker compose up -d --build` (UI on :8080); demo: `docker compose --profile demo up -d --build`. `web` and `poller` are separate services and wait for a one-shot `migrate` service — polling must not be added to the web process.
- Production stack: `docker-compose.prod.yml` pulls an immutable image, requires `APP_IMAGE`/`APP_VERSION` and real secrets, runs migrations once via a one-shot `migrate` service, and does not expose PostgreSQL. The Dockerfile builds the WhiteNoise manifest at build time; production does not run `collectstatic` at startup.
- Release/deploy: bump every `APP_VERSION` marker, run `python scripts/check_version.py X.Y.Z`, then tag `vX.Y.Z`. `release.yml` publishes to GHCR, smoke-tests the production stack and calls `deploy.yml`; `main-deploy.yml` deploys every successful CI run on `main` straight to production (staging is removed). Deployment runs on the self-hosted Windows runner (`self-hosted, Windows, X64, mrw`), builds the image locally, writes the env file from the `ENV_FILE_CONTENT` environment secret, and calls `deploy.ps1 -SkipPull`. `deploy.ps1` `pg_dump`s the DB (14 kept) and auto-rolls back to the previous tag when `/api/ready` or the poller heartbeat fails. Production uses `docker-compose.selfhosted.yml` and adopts the existing `multiregistrator-*` containers/volumes. See `docs/DEPLOYMENT.md`.

## Architecture and gotchas

- `ARCHIVE_STORAGE=files|database|both` controls writes and reads. With `files`, no `Measurement` rows are written; with `both`, reads come from the DB. File-mode tests must use `override_settings` and reset `devices.storage._writer`/`_reader` (see `devices/tests/test_models_storage.py`).
- `Measurement.channel` stores the channel name, not an FK: renaming a `Channel` leaves old rows under the old name and hides that history from charts/API. Treat names as stable or migrate existing rows.
- CSV archive timestamps are naive local time (`DJANGO_TIME_ZONE`; local settings default UTC, Docker/.env default `Europe/Moscow`); DB timestamps are aware UTC (`USE_TZ=True`). In Docker, `web` and `poller` share the `archive-data` volume, which `files`/`both` relies on.
- `devices/modbus.py` supports both current `device_id=` and legacy pymodbus `slave=` keyword arguments; keep that fallback when changing Modbus calls. `settings.MODBUS_MAX_REGISTERS` is currently unused: block size is `MAX_REGISTERS_PER_REQUEST=125` in `devices/modbus.py`.
- Poller heartbeat: the `PollerHeartbeat` singleton is updated every 5s; `python manage.py poller_health --max-age 120` is the poller Docker healthcheck and deploy gate. Keep heartbeat updates inside the per-device loop so a long poll does not look like a dead poller.
- APIs are plain Django `JsonResponse` views (no DRF) in `devices/views.py`, routed in `devices/urls.py`. API paths have no trailing slash; page paths do. `/api/health` is liveness; `/api/ready` checks the DB and is used by production healthchecks. `/api/*` is intentionally public for integrations; page views use `@login_required`. Logout is POST-only. `_resolve_device` takes a numeric PK first, then falls back to `host`, for all `/api/devices/{id}` routes.
- `UserActionLogMiddleware` logs GET page views and ignores `/api/`, `/static/`, `/media/`, `/admin/`. `api_data` logs a chart event unless `reason=live`; live polling must stay out of `UserEventLog`. Audit writes are best-effort (`audit.log_event` swallows DB errors) and `AUDIT_LOG_ENABLED=0` disables them.
- The dashboard and `/api/devices/{id}/latest` serve the `Device.latest_values`/`channel_availability` snapshot written by the poller, not `Measurement` rows; a stopped poller keeps showing the last snapshot with a stale `last_success`.
- Chart code: `devices/static/devices/chart-utils.js` is a UMD module shared by the browser and Node tests; `chart.js` holds the Chart.js integration and live polling. Keep exports, JS tests and script order (`chart-utils` before `chart`) in sync. Chart.js/zoom/Hammer assets are vendored under `devices/static/devices/vendor/`; there is no bundler.
- Channel scan/search lives in `DeviceAdmin` (`devices/admin.py`) and `devices/discovery.py`; it probes only holding/input and proposes plausible `float32` candidates. Other channel types are configured manually.
- Key modules: `devices/archive.py` implements the CSV format, `devices/simulator.py` is the Modbus TCP test server, and `devices/apps.py` registers the auth audit signals.
- Shared test fixture: `make_device()` in `devices/tests/test_models_storage.py` creates a device plus one `float32` channel and is imported by other test modules.
- The demo register map is defined in `devices/management/commands/seed_demo.py` and `test_device.py`, and exercised in `devices/tests/test_simulator.py`; update them together.
- `APP_VERSION` defaults are duplicated in `multiregistrator_web/settings.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `package.json` and `README.md`; `devices/views.py` reads `settings.APP_VERSION` at import time. `scripts/check_version.py` verifies exactly those files (`--current` compares them to settings.py). Run it before tagging and tag `vX.Y.Z` on release.
