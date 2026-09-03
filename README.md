# offline-docker-cli

Универсальная Python CLI для подготовки **offline-cache**, валидации, офлайн-сборки Docker-образов и **Trivy**-сканирования.

CLI **не содержит** конфигов конкретных проектов — всё берётся из целевого репозитория (`--project`).

## Установка

### Вариант A — без pip (рекомендуется в corp-сети)

```powershell
D:\opo\NeuroAI\offline-docker-cli\offline-docker.cmd discover -p D:\opo\NeuroAI\prognoz-np
```

### Вариант B — pip (если PyPI доступен)

```powershell
cd D:\opo\NeuroAI\offline-docker-cli
pip install -e .
pip install -e ".[yaml]"   # опционально: .offline-docker.yaml
offline-docker configure   # ProGet/Nexus URL (Enter = только offline-cache)
```

## Быстрый старт

Сгенерировать черновик конфига (рекурсивный scan) или скопировать шаблон из `examples/`:

```powershell
cd D:\opo\NeuroAI\prognoz-np
offline-docker init -p .          # → .offline-docker.json (или .generated.json)
offline-docker discover -p .
offline-docker download-offline-cache -p .
offline-docker build-offline -p .
offline-docker up-offline -p .
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
offline-docker init -p . --dry-run   # только отчёт
```

## Команды

| Команда | Описание |
|---------|----------|
| `configure` | User-level ProGet/Nexus (или local-only) |
| `init` | Рекурсивный scan → черновик `.offline-docker.json` (+ gaps) |
| `discover` | Compose, Python/npm lock, Dockerfile, APT-пакеты, sources, Missing |
| `download-debs` | Ubuntu `.deb` (+ extra repos) |
| `download-wheels` | Python wheels |
| `download-npm-cache` | npm `_cacache` |
| `download-yarn-cache` | Yarn cache, если в `*Dockerfile.offline` есть `source=yarn` |
| `download-docker-images` | `docker pull` + `save` |
| `download-trivy-db` | Vulnerability DB Trivy |
| `download-offline-cache` | Все download-* подряд |
| `validate-offline-cache` | Проверка полноты кэша |
| `load-docker-images` | `docker load` из `offline-cache/docker/` |
| `build-base-offline` | Базовый образ |
| `build-offline [base backend frontend]` | Офлайн-сборка |
| `up-offline [--lab] [--no-build] [--no-deps] [services]` | Compose up offline-стека |
| `dev-up` | Онлайн: base + compose build + up |
| `scan-trivy-offline <backend\|frontend> [image]` | Trivy scan |

### Общие флаги

- `--project PATH` / `-p` — корень целевого проекта (default: текущий каталог)
- `--config PATH` — явный путь к конфигу (default: `.offline-docker.json` в корне проекта)

Справка и примеры — в `--help` (общий и по команде):

```powershell
offline-docker --help
offline-docker scan-trivy-offline --help
offline-docker up-offline --help
```

## Примеры команд

### Подготовка и сборка

```powershell
# Полный цикл подготовки кэша (на машине с интернетом)
offline-docker download-offline-cache -p D:\opo\NeuroAI\prognoz-np

# На офлайн-машине: загрузить образы и собрать
offline-docker load-docker-images -p .
offline-docker build-offline -p .
offline-docker validate-offline-cache -p .

# Собрать только backend (без base/frontend)
offline-docker build-offline -p . backend
```

### `up-offline` и режим `--lab`

Обычный offline-стек (merge-файлы из `compose_up_offline` в конфиге):

```powershell
offline-docker up-offline -p .
```

Home lab — дополнительно подключается `docker-compose.lab.yml`:

```powershell
offline-docker up-offline -p . --lab
```

Что нужно в **целевом проекте**:

1. Файл `docker-compose.lab.yml` в корне репозитория (override для домашней среды).
2. В `.offline-docker.json` — секция `compose_up_offline_lab` со списком compose-файлов (см. `examples/offline-docker.json.example`). Если секция не задана, CLI сам добавит `docker-compose.lab.yml` к списку из `compose_up_offline`.

Подробнее о полях конфига: [`examples/README.md`](examples/README.md).

Дополнительные флаги:

```powershell
# Не пересобирать образы (уже собраны)
offline-docker up-offline -p . --no-build

# Поднять только backend, без пересоздания зависимостей
offline-docker up-offline -p . --no-deps backend

# Lab + только frontend
offline-docker up-offline -p . --lab frontend
```

### `scan-trivy-offline`

**Обязательный позиционный аргумент** `target`: `backend` или `frontend`.  
Опционально — свой тег образа вместо `images.backend` / `images.frontend` из конфига.

```powershell
# Скан backend-образа из конфига (images.backend)
offline-docker scan-trivy-offline -p . backend

# Скан frontend-образа
offline-docker scan-trivy-offline -p . frontend

# Явный тег образа (если собрали под другим именем)
offline-docker scan-trivy-offline -p . backend myapp-backend:cuda12
```

Перед сканом:

1. Образ должен существовать локально (`docker images`) — обычно после `build-offline`.
2. БД Trivy в `offline-cache/trivy/` — `download-trivy-db` или `download-offline-cache` (на машине с интернетом); на офлайн-машине CLI попытается использовать кэш и предупредит, если БД устарела.
3. Образ сканера `aquasec/trivy:latest` — в `docker_images` конфига, загружается через `load-docker-images`.

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
offline-docker configure
# или без prompt:
offline-docker configure --local-only
offline-docker configure --proget-url https://proget.example.com --nexus-url http://nexus.example.com:8081
```

Конфиг пишется в user-level файл (не в example проекта):

- Linux/macOS: `~/.config/offline-docker/sources.json`
- Windows: `%APPDATA%\offline-docker\sources.json`
- override каталога: `OFFLINE_DOCKER_CONFIG_DIR`

Приоритет: **project `.offline-docker.json` → секция `cache`** перекрывает user-config; иначе user; иначе local-only.

Порядок поиска задаётся `resolve.order` (например `local,proget,nexus`). `download-wheels` / `download-npm-cache` ходят по цепочке index URL и дописывают артефакты в локальную папку (`fill_local`).

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
