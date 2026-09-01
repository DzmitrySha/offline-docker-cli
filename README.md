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
```

## Быстрый старт

В корне **целевого проекта** должен быть `.offline-docker.json` (шаблоны — в `examples/`):

```powershell
cd D:\opo\NeuroAI\prognoz-np
offline-docker discover -p .
offline-docker download-offline-cache -p .
offline-docker build-offline -p .
offline-docker up-offline -p .
```

## Команды

| Команда | Описание |
|---------|----------|
| `discover` | Compose, Python/npm lock, Dockerfile, APT-пакеты |
| `download-debs` | Ubuntu `.deb` (+ extra repos) |
| `download-wheels` | Python wheels |
| `download-npm-cache` | npm `_cacache` |
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

## Env-переменные

| Переменная | Назначение |
|------------|------------|
| `OFFLINE_CACHE` | Путь к offline-cache (override) |
| `{APP_NAME}_OFFLINE_CACHE` | Alias из `app_name` в конфиге |
| `PYTORCH_INDEX` | Index URL для torch wheels |
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

### 1.2.0

- Схема `images`: канонические поля `base`, `backend`, `frontend` (единый тег `cuda12` / `latest` для online и offline).
- Удалены `legacy_base_*` и retag старых образов.
- Старый JSON (`base_online`, `backend_offline`, …) читается при загрузке конфига.
