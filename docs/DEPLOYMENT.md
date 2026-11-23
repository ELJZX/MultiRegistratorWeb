# Выкладка и CI/CD

## Схема

- Pull request -> `CI`: Django-тесты на SQLite и PostgreSQL, JS-тесты, проверка миграций, Docker smoke-тест.
- Merge в `main` -> успешный `CI` -> `Staging`: сборка образа с тегом `sha-<short>`, публикация в GHCR, деплой на staging.
- Тег `vX.Y.Z` -> `Release`: проверка версии и тестов, сборка и публикация `X.Y.Z` + `sha-<short>` в GHCR, smoke-тест production-стека, деплой на production после approve.
- Ручной запуск `Deploy` -> выкладка выбранного тега в `staging` или `production` (откат или hotfix).

Production-образы неизменяемые: выкладка идёт по конкретному тегу, не по `latest`.

Проверка готовности выкладки — `/api/ready` (процесс + БД); `/api/health` остаётся liveness-проверкой. Дополнительно `poller` пишет heartbeat, а `deploy.ps1` и Docker healthcheck проверяют его командой `python manage.py poller_health --max-age 120`.

## Требования к Windows VM

- Docker Desktop в режиме **Linux containers** (WSL2). Windows containers не подходят.
- Включён OpenSSH Server, порт доступен только с доверенных адресов.
- Docker Desktop запускается автоматически. Для полностью unattended-работы нужен автологин пользователя либо переход на Linux VM с Docker Engine.
- На VM выполнена команда `docker login ghcr.io` с PAT, у которого есть только `read:packages`; либо пакет GHCR сделан публичным.
- Каталог выкладки, например `C:/multiregistrator`, без пробелов в пути:
  - `.env.production` и `.env.staging` — секреты и параметры;
  - `docker-compose.prod.yml` и `deploy.ps1` — обновляются workflow автоматически;
  - `backups/` — дампы PostgreSQL;
  - `.deployed-version.<project>` — последняя успешная версия для отката.

Docker Desktop на Windows — не серверный runtime. Если нужна круглосуточная предсказуемая работа без зависимости от интерактивной сессии, используйте Linux VM с Docker Engine; workflow деплоя меняется только в части транспорта.

## GitHub Environments

Создайте окружения `staging` и `production`. Для `production` включите Required reviewers.

В каждом окружении задайте секреты:

| Секрет | Назначение |
| --- | --- |
| `DEPLOY_HOST` | IP или DNS Windows VM |
| `DEPLOY_USER` | пользователь SSH |
| `DEPLOY_PATH` | каталог выкладки, например `C:/multiregistrator` |
| `DEPLOY_SSH_KEY` | приватный ключ без пароля |
| `DEPLOY_KNOWN_HOSTS` | строка из `ssh-keyscan -t ed25519 <host>` |

Публичный ключ добавьте в `C:\Users\<user>\.ssh\authorized_keys` на VM.

## Переменные на VM

`.env.production` и `.env.staging` должны содержать как минимум:

```dotenv
APP_IMAGE=ghcr.io/eljzx/multiregistrator-web
APP_VERSION=<version>
DJANGO_SECRET_KEY=<длинный случайный ключ>
DJANGO_ALLOWED_HOSTS=meters.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://meters.example.com
POSTGRES_DB=multiregistrator
POSTGRES_USER=multiregistrator
POSTGRES_PASSWORD=<сильный пароль>
WEB_PORT=8080
ARCHIVE_STORAGE=database
AUDIT_LOG_ENABLED=1
```

Для staging на той же VM используйте отдельные `.env.staging`, `WEB_PORT` (например, `8081`) и project name `multiregistrator-staging`; workflow передаёт его через `-p`. Контейнеры и volumes будут разделены по имени проекта.

`APP_VERSION` в файле — значение по умолчанию. Workflow передаёт конкретную версию в `deploy.ps1`, и она имеет приоритет.

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
- либо на VM:

  ```powershell
  $env:APP_VERSION = "1.2.0"
  docker compose -f docker-compose.prod.yml --env-file .env.production -p multiregistrator up -d
  ```

Миграции должны быть backward-compatible. Если новая миграция разрушительная, автоматический откат кода не восстановит данные — нужен restore из дампа.

## Бэкапы

Перед каждой выкладкой `deploy.ps1`:

- делает `pg_dump -Fc` в `backups/db_<timestamp>.dump`;
- хранит последние 14 дампов (`-BackupRetention`);
- не начинает выкладку, если БД уже развёрнута, но контейнер `db` не запущен.

Дампы лежат на той же VM, поэтому их нужно регулярно копировать на другой носитель. Восстановление:

```powershell
docker compose -f docker-compose.prod.yml --env-file .env.production -p multiregistrator stop web poller
docker compose -f docker-compose.prod.yml --env-file .env.production -p multiregistrator cp "backups\db_20260101_120000.dump" db:/tmp/restore.dump
docker compose -f docker-compose.prod.yml --env-file .env.production -p multiregistrator exec -T db pg_restore -U multiregistrator -d multiregistrator --clean --if-exists /tmp/restore.dump
docker compose -f docker-compose.prod.yml --env-file .env.production -p multiregistrator up -d
```

Перед restore проверьте имя пользователя и базы из `.env.production`.
