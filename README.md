# offline-docker-cli

**Для агентов:** [`AGENTS.md`](AGENTS.md) · площадка: `d:\opo\NeuroAI\all_NeuroAI\docs\PLATFORM.md`.

Универсальная Python CLI (**`offdock`**) для подготовки **offline-cache**, валидации, офлайн-сборки Docker-образов и **Trivy**-сканирования.

CLI **не содержит** конфигов конкретных проектов — всё берётся из целевого репозитория (`--project`).

**2.1.0:** удалены deprecated aliases старых команд и entrypoint `offline-docker` (только `offdock`).
**2.0.0 (breaking):** бинарь `offdock`, короткие команды (`cache`, `build`, `up`, `down`, `scan`).

## Установка

### Вариант A — без pip (рекомендуется в corp-сети)

```powershell
D:\opo\NeuroAI\offline-docker-cli\offdock.cmd discover -p D:\opo\NeuroAI\prognoz_np
```

### Вариант B — pip (если PyPI доступен)

```powershell
cd D:\opo\NeuroAI\offline-docker-cli
pip install -e .
pip install -e ".[yaml]"   # опционально: .offline-docker.yaml
pip install -e ".[tui]"    # опционально: Textual TUI
offdock configure          # ProGet/Nexus URL (Enter = только offline-cache)
```

### Опциональный TUI

Терминальный UI поверх тех же команд (статус кэша, меню, live-лог). CLI остаётся основным интерфейсом.

```powershell
# Установка (для использования — без -e, чтобы пакет жил в site-packages)
pip install D:\opo\NeuroAI\offline-docker-cli\[tui]

# Запуск
offdock tui -p .
```

**Важно:** `pip install -e ".[tui]"` (editable) привязывает пакет к папке исходников — если папку переместить/удалить, CLI сломается. Для использования рекомендуется **обычная установка** (без `-e`).  
Для разработки самого CLI — тогда `-e`.

## Быстрый старт

Сгенерировать черновик конфига (рекурсивный scan) или скопировать шаблон из `examples/`:

```powershell
cd D:\opo\NeuroAI\prognoz-np
offdock init -p .          # → .offline-docker.json (или .generated.json)
offdock discover -p .
offdock cache -p .
offdock cache check -p .   # проверка полноты offline-cache
offdock build -p .
offdock up -p .
```

### `init` — черновик конфига

Рекурсивно ищет compose, Dockerfile, python/frontend lock-файлы и пишет JSON по схеме example.

| Ситуация | Файл |
|----------|------|
| Нет `.offline-docker.json` / `.yaml` | создаётся `.offline-docker.json` |
| Канон уже есть | пишется `.offline-docker.generated.json` (канон **не** затирается) |

В JSON есть секция `_init.gaps` и в stdout — блок `Missing / to fix:` (нет `Dockerfile.*.offline`, offline-compose и т.д.).  
**Не** генерируются сами offline-Dockerfile / compose — только пути и список доработок.

```powershell
offdock init -p . --dry-run   # только отчёт
```

## Команды

| Команда | Описание |
|---------|----------|
| `configure` | User-level ProGet/Nexus (или local-only) |
| `tui` | Интерактивный Textual TUI (нужен `pip install …[tui]`) |
| `init` | Рекурсивный scan → черновик `.offline-docker.json` (+ gaps) |
| `discover` | Compose, Python/npm lock, Dockerfile, APT-пакеты, sources, Missing |
| `cache` | Полный download offline-cache |
| `cache wheels\|debs\|npm\|yarn\|images\|trivy` | Частичный download |
| `cache check` | Проверка полноты кэша |
| `cache load` | `docker load` из `offline-cache/docker/` |
| `build [base backend frontend]` | Офлайн-сборка |
| `up [--lab\|--online] […]` | Compose up (offline / lab / online) |
| `down [--lab\|--online] [services]` | Compose down того же стека |
| `scan [trivy] <backend\|frontend> [image]` | Скан образа (default: trivy) |

### Общие флаги

- `--project PATH` / `-p` — корень целевого проекта (default: текущий каталог)
- `--config PATH` — явный путь к конфигу (default: `.offline-docker.json` в корне проекта)

Справка и примеры — в `--help` (общий и по команде):

```powershell
offdock --help
offdock scan --help
offdock up --help
```

## Примеры команд

### Подготовка и сборка

```powershell
# Полный цикл подготовки кэша (на машине с интернетом)
offdock cache -p D:\opo\NeuroAI\prognoz-np

# На офлайн-машине: загрузить образы и собрать
offdock cache load -p .
offdock build -p .
offdock cache check -p .

# Собрать только backend (без base/frontend)
offdock build -p . backend
```

### `up` / `down` и режимы `--lab` / `--online`

Обычный offline-стек (merge-файлы из `compose_up_offline` в конфиге):

```powershell
offdock up -p .
offdock down -p .
```

Home lab — дополнительно подключается `docker-compose.lab.yml`:

```powershell
offdock up -p . --lab
offdock down -p . --lab
```

Online — только `compose_online`:

```powershell
offdock up -p . --online
offdock down -p . --online
```

Что нужно в **целевом проекте** для `--lab`:

1. Файл `docker-compose.lab.yml` в корне репозитория (override для домашней среды).
2. В `.offline-docker.json` — секция `compose_up_offline_lab` со списком compose-файлов (см. `examples/offline-docker.json.example`). Если секция не задана, CLI сам добавит `docker-compose.lab.yml` к списку из `compose_up_offline`.

Подробнее о полях конфига: [`examples/README.md`](examples/README.md).

Дополнительные флаги:

```powershell
# Не пересобирать образы (уже собраны)
offdock up -p . --no-build

# Поднять только backend, без пересоздания зависимостей
offdock up -p . --no-deps backend

# Lab + только frontend
offdock up -p . --lab frontend

# Остановить отдельные сервисы
offdock down -p . backend frontend
```

### `scan`

**Обязательный** target: `backend` или `frontend`.  
Опционально — сканер (`trivy`, default) и тег образа.

```powershell
# Скан backend-образа из конфига (images.backend)
offdock scan backend

# Явно указать сканер
offdock scan trivy frontend

# Явный тег образа
offdock scan trivy backend myapp-backend:cuda12
```

Перед сканом:

1. Образ должен существовать локально (`docker images`) — обычно после `build`.
2. БД Trivy в `offline-cache/trivy/` — `cache trivy` или `cache` (на машине с интернетом); на офлайн-машине CLI попытается использовать кэш и предупредит, если БД устарела.
3. Образ сканера `aquasec/trivy:latest` — в `docker_images` конфига, загружается через `cache load`.

Параметры сканирования (`severity`, `scanners`, `db_max_age_days`) — в секции `trivy` конфига:

```json
"trivy": {
  "scanner_image": "aquasec/trivy:latest",
  "db_max_age_days": 7,
  "severity": "HIGH,CRITICAL",
  "scanners": "vuln"
}
```

Лог пишется в `{log_dir}/trivy-scan-{backend|frontend}.log` (default: `storage/logs/`).

## Конфигурация целевого проекта

1. **`.offline-docker.json`** (или `.offline-docker.yaml`) в корне репозитория — **канон**
2. **Auto-discovery** — fallback, если конфига нет (для `discover`; для build рекомендуется конфиг)

Пример: `examples/offline-docker.json.example` — скопируйте в корень проекта как `.offline-docker.json`.

## Источники пакетов (local / ProGet / Nexus)

По умолчанию CLI использует **только локальный** `offline-cache/`.

После установки настройте корпоративные реестры (один раз на машину):

```powershell
offdock configure
# заполнение кэша с интернета (local + PyPI/npmjs):
offdock configure --with-upstream
# только offline-cache (корп/офлайн VM):
offdock configure --local-only
offdock configure --proget-url https://proget.example.com --nexus-url http://nexus.example.com:8081
```

Конфиг пишется в user-level файл (не в example проекта):

- Linux/macOS: `~/.config/offline-docker/sources.json`
- Windows: `%APPDATA%\offline-docker\sources.json`
- override каталога: `OFFLINE_DOCKER_CONFIG_DIR`

Приоритет: **project `.offline-docker.json` → секция `cache`** перекрывает user-config; иначе user; иначе local-only.

| Режим | Когда |
|-------|--------|
| `--with-upstream` | Машина с сетью: `cache` / `cache wheels` тянет с PyPI/npmjs в `offline-cache/` |
| `--local-only` | Офлайн/корп VM: сборка только из уже скачанного кэша |
| ProGet/Nexus | Корп. зеркала; порядок в `resolve.order` |

Порядок поиска задаётся `resolve.order` (например `local,upstream` или `local,proget,nexus`). `cache wheels` / `cache npm` ходят по цепочке index URL и дописывают артефакты в локальную папку (`fill_local`).

Если в `sources.json` стоит **local-only**, `cache wheels` всё равно временно добавляет PyPI/PyTorch (с WARN) и перед скачиванием удаляет **устаревшие** wheels, чья версия не совпадает с pin в lock/requirements (типичный случай `protobuf==7.x` при старом `6.x` в кэше).

Auth (опционально, через env, не в JSON): `PROGET_API_KEY`, `NEXUS_AUTH` (`user:pass` или Bearer).

Для Nexus по HTTP pip автоматически получает `--trusted-host`; npm — `strict-ssl false`.

Env: `OFFLINE_RESOLVE_ORDER=local,proget,nexus` — временный override порядка.

Шаблон проекта (`examples/offline-docker.json.example`) **нейтральный** — без корпоративных URL.

## Env-переменные

| Переменная | Назначение |
|------------|------------|
| `OFFLINE_CACHE` | Путь к offline-cache (override) |
| `{APP_NAME}_OFFLINE_CACHE` | Alias из `app_name` в конфиге |
| `OFFLINE_DOCKER_CONFIG_DIR` | Каталог user-config (`sources.json`) |
| `OFFLINE_RESOLVE_ORDER` | Порядок sources через запятую |
| `PROGET_API_KEY` / `NEXUS_AUTH` | Auth для remote |
| `PYTORCH_INDEX` | Index URL для torch wheels |
| `PYPI_INDEX` | Force primary PyPI index |
| `DOCKER_BUILDKIT` | `1` для build |

## Структура репозитория

```
offline-docker-cli/
├── pyproject.toml
├── README.md
├── examples/              # шаблоны .offline-docker.json
└── src/offline_docker/
    ├── cli.py
    ├── config.py
    ├── discover.py
    └── ...
```

## Требования

- Python 3.11+
- Docker (CLI на PATH)

## Changelog

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
