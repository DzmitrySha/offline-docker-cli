# Changelog

### 2.2.2

- `cache debs`: кэш привязан к дистрибутиву гостевого образа — в `debs/.base-os` пишется `<ID>-<VERSION_ID>`; при смене базы (например, `python:3.12-slim` bookworm → trixie) старые `.deb` удаляются автоматически вместо смешивания Ubuntu/Debian пакетов.

### 2.2.1

- `cache wheels`: python берётся из базового образа (`debs.ubuntu_image`), а не ставится из apt. Пакеты `python3.12*` в Debian 13 (trixie) отсутствуют, из-за чего `python:3.12-slim` падал на `apt-get install` и wheels не скачивались.
- Проверка ABI: если python в образе старее `requires-python` проекта, `cache wheels` падает с явной ошибкой вместо wheel-ов для чужой версии.

### 2.2.0

- `hooks.after_cache` в `.offline-docker.json`: win/sh/script хуки после `cache` / перед offline-сборкой (vendor binaries и т.п.).
- `validation.critical_vendor` — проверка критичных vendor-артефактов в статусе кэша.
- `AGENTS.md` — правила для агентов при работе с CLI.

### 2.1.0

- Удалены deprecated aliases старых subcommands (`download-*`, `build-offline`, `up-offline`, `dev-up`, `scan-trivy-offline`, …).
- Удалён entrypoint `offline-docker` из `pyproject.toml` — только `offdock`.

### 2.0.0

- Бинарь **`offdock`**.
- Короткие команды: `cache` (+ подкоманды), `build`, `up`, `down`, `scan [trivy]`.
- `up --online` вместо `dev-up`; `up --lab` без переименования смысла.
- Новая команда `down` с теми же режимами и поддержкой services.

### 1.4.2

- `configure --with-upstream`: явный режим local + PyPI/npmjs для заполнения кэша с сети.
- Пустые ProGet/Nexus URL больше не пишут silent local-only — по умолчанию `local,upstream`.
- `download-wheels`: WARN при local-only fallback; prune устаревших wheels по pin; retry без `--find-links`; `--retries`/`--timeout`.
- `download-npm-cache`: WARN, если registry взят по умолчанию при local-only.

### 1.4.1

- `download-npm-cache`: гостевой скрипт в `node:*-slim` идёт через `/bin/sh` (dash) — без `set -o pipefail` (иначе `Illegal option -o pipefail`).
- `offline-docker --version` / `-V`; `__version__` синхронизирован с `pyproject.toml`.

### 1.4.0

- Опциональный Textual TUI: `offline-docker tui` (`pip install -e ".[tui]"`) — статус кэша, меню команд, live-лог.
- Общий слой `actions` / structured `collect_cache_status` для CLI и TUI.

### 1.3.0

- Мульти-источники пакетов: local → ProGet → Nexus (порядок в `resolve.order`).
- Команда `offline-docker configure` (user-level `sources.json`; пустые URL = local-only).
- `download-wheels` / `download-npm-cache` / `download-debs` используют цепочку index URL.
- Best-effort materialize/publish для Nexus raw и ProGet universal (`publish: true`).
- `discover` печатает активные sources.

### 1.2.0

- Схема `images`: канонические поля `base`, `backend`, `frontend` (единый тег `cuda12` / `latest` для online и offline).
- Удалены `legacy_base_*` и retag старых образов.
- Старый JSON (`base_online`, `backend_offline`, …) читается при загрузке конфига.
