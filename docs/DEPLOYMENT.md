# Выкладка и CI/CD

## Схема

- Pull request -> `CI`: Django-тесты на SQLite и PostgreSQL, JS-тесты, проверка миграций, Docker smoke-тест.
- Merge в `main` -> успешный `CI` -> `Staging`: сборка образа с тегом `sha-<short>`, публикация в GHCR, деплой на staging.
- Тег `vX.Y.Z` -> `Release`: проверка версии и тестов, сборка и публикация `X.Y.Z` + `sha-<short>` в GHCR, smoke-тест production-стека, деплой на production после approve.
- Ручной запуск `Deploy` -> выкладка выбранного тега в `staging` или `production` (откат или hotfix).

Production-образы неизменяемые: выкладка идёт по конкретному тегу, не по `latest`.

Деплой выполняется на self-hosted GitHub Actions runner, который работает на том же Windows-хосте с Docker Desktop. SSH и отдельная VM больше не нужны. Runner собирает образ локально из проверенного commit и запускает `deploy.ps1 -SkipPull`, поэтому `docker login` в GHCR для деплоя не требуется. Публикация образов в GHCR в jobs `Staging`/`Release` сохраняется для распространения и smoke-тестов.

Проверка готовности выкладки — `/api/ready` (процесс + БД); `/api/health` остаётся liveness-проверкой. Дополнительно `poller` пишет heartbeat, а `deploy.ps1` и Docker healthcheck проверяют его командой `python manage.py poller_health --max-age 120`.

## Требования к хосту

- Docker Desktop в режиме **Linux containers** (WSL2). Windows containers не подходят.
- GitHub Actions self-hosted runner с метками `self-hosted`, `Windows`, `X64`, `mrw`.
- Runner запускается в пользовательской сессии, где работает Docker Desktop. Не устанавливайте его как службу `LocalSystem`: у такой службы обычно нет доступа к Docker Desktop.
- Автозапуск runner — через ярлык/скрипт в папке Startup пользователя. Docker Desktop также должен запускаться при входе.
- Каталоги выкладки:
  - `D:\multiregistrator` — production; использует существующие volume `multiregistratorweb_*` и сеть `hub_multiregistator`;
  - `D:\multiregistrator-staging` — staging на отдельном порту.
- В каталогах выкладки workflow создаёт `.env.production`/`.env.staging`, `docker-compose*.yml`, `deploy.ps1`, `backups/` и `.deployed-version.<project>`.

## GitHub Environments

Создайте окружения `staging` и `production`. Для `production` включите Required reviewers.

В каждом окружении задайте секреты:

| Секрет | Назначение |
| --- | --- |
| `DEPLOY_PATH` | локальный каталог выкладки, например `D:\multiregistrator` |
| `ENV_FILE_CONTENT` | полное содержимое `.env.production` или `.env.staging` |

SSH-секреты (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`) больше не используются.

## Self-hosted runner

Регистрация (нужны права администратора репозитория):

```powershell
$token = gh api --method POST repos/ELJZX/MultiRegistratorWeb/actions/runners/registration-token --jq .token
cd D:\actions-runner-multiregistrator
.\config.cmd --unattended `
  --url https://github.com/ELJZX/MultiRegistratorWeb `
  --token $token `
  --name mrw-dockerdesktop `
  --labels self-hosted,windows,x64,mrw `
  --work _work `
  --runnergroup Default `
  --replace
```

Запуск:

```powershell
.\run.cmd
```

Для автозапуска положите в `shell:startup` скрипт, который запускает `D:\actions-runner-multiregistrator\run.cmd` скрыто. Проверка статуса:

```powershell
gh api repos/ELJZX/MultiRegistratorWeb/actions/runners
```

## Файлы окружения

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

`APP_VERSION` в файле — значение по умолчанию. Workflow передаёт конкретную версию в `deploy.ps1`, и она имеет приоритет.

Production использует `docker-compose.selfhosted.yml`: он намеренно сохраняет имена контейнеров `multiregistrator-*`, volume `multiregistratorweb_*` и сеть `hub_multiregistator`, поэтому обновление не теряет базу. Staging использует `docker-compose.prod.yml` с отдельным project name и портом.

При первом переключении production на этот compose сохраните прежний `POSTGRES_PASSWORD`: PostgreSQL не меняет пароль существующего volume при изменении переменной.

## Релиз

1. Обновите версию во всех местах:
   - `multiregistrator_web/settings.py`
   - `Dockerfile`
   - `docker-compose.yml`
   - `.env.example`
   - `package.json`
   - `README.md`
2. Проверьте согласованность:

   ```bash
   python scripts/check_version.py 1.3.0
   ```

3. Закоммитьте изменения и поставьте тег:

   ```bash
   git tag v1.3.0
   git push origin main --tags
   ```

4. Дождитесь approve окружения `production`.

## Откат

При неудачном healthcheck `deploy.ps1` автоматически возвращает предыдущий тег из `.deployed-version.<project>` и поднимает стек заново.

Ручной откат:

- запустите workflow `Deploy` с `environment=production` и предыдущим `version`;
- либо на хосте:

  ```powershell
  $env:APP_VERSION = "1.2.0"
  docker compose -f docker-compose.selfhosted.yml --env-file .env.production -p multiregistratorweb up -d
  ```

Миграции должны быть backward-compatible. Если новая миграция разрушительная, автоматический откат кода не восстановит данные — нужен restore из дампа.

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
