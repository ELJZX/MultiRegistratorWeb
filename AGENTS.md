# AGENTS.md

Django 5 + Modbus TCP data logger. Django project package: `multiregistrator_web`; the only local app is `devices`. UI text, admin labels, command help and `README.md` are Russian — keep new user-facing strings Russian. `README.md` is the detailed reference for env vars, API, storage modes and the demo flow.

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
python manage.py test             # Django suite; simulator tests use real localhost sockets
python manage.py test devices.tests.test_modbus.DecodeTests.test_uint16
npm run test:js                   # Node 18+; no npm install or frontend build
```

- `manage.py test` does not run the JS tests. There is no lint/format/typecheck/CI config; those two test commands are the available checks.
- Local default DB is SQLite; setting `DB_HOST` switches to PostgreSQL. Docker uses PostgreSQL 16.
- Docker: `docker compose up -d --build` (UI on :8080); demo: `docker compose --profile demo up -d --build`. `web` and `poller` are separate services — polling must not be added to the web process.

## Architecture and gotchas

- `ARCHIVE_STORAGE=files|database|both` controls writes and reads. With `files`, no `Measurement` rows are written; with `both`, reads come from the DB. File-mode tests must use `override_settings` and reset `devices.storage._writer`/`_reader` (see `devices/tests/test_models_storage.py`).
- CSV archive timestamps are naive local time (`DJANGO_TIME_ZONE`); DB timestamps are aware UTC (`USE_TZ=True`).
- `devices/modbus.py` supports both current `device_id=` and legacy pymodbus `slave=` keyword arguments; keep that fallback when changing Modbus calls.
- APIs are plain Django `JsonResponse` views (no DRF) in `devices/views.py`, routed in `devices/urls.py`. API paths have no trailing slash; page paths do. `/api/*` is intentionally public for integrations; page views use `@login_required`. Logout is POST-only.
- `UserActionLogMiddleware` logs GET page views and ignores `/api/`, `/static/`, `/media/`, `/admin/`. `api_data` logs a chart event unless `reason=live`; live polling must stay out of `UserEventLog`.
- Chart code: `devices/static/devices/chart-utils.js` is a UMD module shared by the browser and Node tests; `chart.js` holds the Chart.js integration and live polling. Keep exports, JS tests and script order (`chart-utils` before `chart`) in sync. Chart.js/zoom/Hammer assets are vendored under `devices/static/devices/vendor/`; there is no bundler.
- Shared test fixture: `make_device()` in `devices/tests/test_models_storage.py` creates a device plus one `float32` channel and is imported by other test modules.
- The demo register map is defined in `devices/management/commands/seed_demo.py` and `test_device.py`, and exercised in `devices/tests/test_simulator.py`; update them together.
- `APP_VERSION` defaults are duplicated in `multiregistrator_web/settings.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `package.json` and `README.md` (there is also a stale `1.1.0` fallback in `devices/views.py`). Update all and tag `vX.Y.Z` on release.
