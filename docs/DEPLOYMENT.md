# Выкладка и CI/CD

## Схема

- Pull request -> `CI`: Django-тесты на SQLite и PostgreSQL, JS-тесты, проверка миграций, Docker smoke-тест.
- Merge/push в `main` -> успешный `CI` -> `Main deploy`: self-hosted runner собирает образ `sha-<short>` и **сразу обновляет production** `multiregistratorweb` на порту `8010`.
- Тег `vX.Y.Z` -> `Release`: проверка версии и тестов, публикация образа в GHCR, smoke-тест и выкладка той же production-копии.
- Ручной запуск `Deploy` -> выкладка выбранной версии в production или откат.

Отдельного staging-окружения больше нет. Production обновляется автоматически после каждого успешного CI на `main`; это осознанный выбор, поэтому тесты и smoke-проверка CI обязательны.

Деплой выполняется на self-hosted GitHub Actions runner на том же Windows-хосте с Docker Desktop. SSH и отдельная VM не нужны. Runner собирает образ локально из проверенного commit и запускает `deploy.ps1 -SkipPull`; `docker login` в GHCR для деплоя не требуется. Публикация в GHCR в job `Release` остаётся для распространения образов.

Проверка готовности выкладки — `/api/ready` (процесс + БД); `/api/health` остаётся liveness-проверкой. `poller` пишет heartbeat, `deploy.ps1` проверяет его командой `python manage.py poller_health --max-age 120`.

## Требования к хосту

- Docker Desktop в режиме **Linux containers** (WSL2).
- Self-hosted GitHub Actions runner с метками `self-hosted`, `Windows`, `X64`, `mrw`.
- Runner запускается в пользовательской сессии, где работает Docker Desktop. Не устанавливайте его службой `LocalSystem`: у службы обычно нет доступа к Docker Desktop.
- Автозапуск runner — через скрипт в папке Startup пользователя. Docker Desktop نیز должен запускаться при входе.
- Каталог production-выкладки: `D:\multiregistrator`.
- В каталоге workflow создаёт `.env.production`, `docker-compose*.yml`, `deploy.ps1`, `backups/` и `.deployed-version.multiregistratorweb`.
- Production использует существующие volume `multiregistratorweb_*` и сеть `hub_multiregistator`, поэтому обновление не теряет базу.

## GitHub Environments

Используется окружение `production`. Для автодеплоя в нём **не должно быть Required reviewers** — иначе `Main deploy` остановится на ожидании approve.

Секреты окружения:

| Секрет | Назначение |
| --- | --- |
| `DEPLOY_PATH` | локальный каталог выкладки, например `D:\multiregistrator` |
| `ENV_FILE_CONTENT` | полное содержимое `.env.production` |

SSH-секреты не используются.

Если позже понадобится ручное подтверждение production, включите Required reviewers — после этого автодеплой будет ждать approve.

## Self-hosted runner

Регистрация (нужны права администратора репозитория):

```powershell
$token = gh api --method POST repos/ELJZX/MultiRegistratorWeb/actions/runners/registration-token --jq .token
cd D:\actions-runner-multiregistrator
.\config.cmd --unattended `
  --url https://github.com/ELJZX/MultiRegistratorWeb `
  --token $token `
  --name mrw-dockerdesktop `
  --labels self-hosted,Windows,X64,mrw `
  --work _work `
  --runnergroup Default `
  --replace
```

Запуск:

```powershell
.\run.cmd
```

Для автозапуска положите в `shell:startup` скрипт, который запускает `D:\actions-runner-multiregistrator\run.cmd` скрыто. Проверка:

```powershell
gh api repos/ELJZX/MultiRegistratorWeb/actions/runners
```

## Файл окружения

Пример `.env.production`:

```dotenv
APP_IMAGE=multiregistrator-web
APP_VERSION=1.2.0
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<длинный случайный ключ>
DJANGO_ALLOWED_HOSTS=*
DJANGO_CSRF_TRUSTED_ORIGINS=
DJANGO_TIME_ZONE=Europe/Moscow
POSTGRES_DB=multiregistrator
POSTGRES_USER=multiregistrator
POSTGRES_PASSWORD=<пароль>
POSTGRES_PORT=5434
WEB_PORT=8010
ARCHIVE_STORAGE=database
AUDIT_LOG_ENABLED=1
```

Workflow подменяет `APP_IMAGE` на локальный `multiregistrator-web` и передаёт конкретный `APP_VERSION`; значения в файле — запасные для ручного запуска.

При первом переключении сохраните прежний `POSTGRES_PASSWORD`: PostgreSQL не меняет пароль существующего volume при изменении переменной.

## Как выкатить

Обычный путь:

1. Смержить изменения в `main`.
2. Дождаться успешного `CI`.
3. `Main deploy` автоматически обновит `multiregistratorweb` на 8010.

Ручной путь: запустить workflow `Deploy` с нужной версией. Для релизного тега:

1. Обновить версию в `multiregistrator_web/settings.py`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `package.json`, `README.md`.
2. Проверить:
   ```bash
   python scripts/check_version.py 1.3.0
   ```
3. Поставить и запушить тег:
   ```bash
   git tag v1.3.0
   git push origin main --tags
   ```

## Откат

При неудачном healthcheck `deploy.ps1` автоматически возвращает предыдущий тег из `.deployed-version.multiregistratorweb` и поднимает стек заново.

Ручной откат — запустить workflow `Deploy` с предыдущей версией. Либо на хосте:

```powershell
$env:APP_VERSION = "1.2.0"
docker compose -f docker-compose.selfhosted.yml --env-file .env.production -p multiregistratorweb up -d
```

Миграции должны быть backward-compatible. Если миграция разрушительная, откат кода не восстановит данные — нужен restore из дампа.

## Бэкапы

Перед каждой выкладкой `deploy.ps1`:

- делает `pg_dump -Fc` в `backups/db_<timestamp>.dump`;
- хранит последние 14 дампов (`-BackupRetention`);
- не начинает выкладку, если БД уже развёрнута, но контейнер `db` не запущен.

Дампы лежат на том же хосте, поэтому их нужно регулярно копировать на другой носитель. Восстановление:

```powershell
docker compose -f docker-compose.selfhosted.yml --env-file .env.production -p multiregistratorweb stop web poller
docker compose -f docker-compose.selfhosted.yml --env-file .env.production -p multiregistratorweb cp "backups\db_20260101_120000.dump" db:/tmp/restore.dump
docker compose -f docker-compose.selfhosted.yml --env-file .env.production -p multiregistratorweb exec -T db pg_restore -U multiregistrator -d multiregistrator --clean --if-exists /tmp/restore.dump
docker compose -f docker-compose.selfhosted.yml --env-file .env.production -p multiregistratorweb up -d
```

Перед restore проверьте имя пользователя и базы из `.env.production`.
