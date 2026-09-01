# Шаблон `.offline-docker.json`

Универсальный пример для любого проекта NeuroAI (backend + frontend, slim CUDA base, offline-cache).

## Установка в проект

```bash
cp examples/offline-docker.json.example /path/to/your-project/.offline-docker.json
```

Затем отредактируйте под свой репозиторий:

| Поле | Что заменить |
|------|----------------|
| `app_name` | короткое имя приложения (для env `{APP_NAME}_OFFLINE_CACHE`) |
| `images.base` | shared base (`neuroai-base:cuda12` для NeuroAI) |
| `images.backend` / `images.frontend` | теги app-образов (`*:latest`) |
| `debs.packages` | APT-пакеты из `Dockerfile.base` / `Dockerfile` |
| `debs.extra_repos` | при необходимости (напр. Microsoft ODBC) |
| `docker_images` | базовые образы для `docker load` (redis, trivy и т.д.) |
| `validate.critical_wheels` | обязательные wheel для validate |
| `compose_up_offline_lab` | удалите, если нет `docker-compose.lab.yml` |

## Проверка

```bash
offline-docker discover -p /path/to/your-project
```

## Секции конфига

- **compose_build** — merge-файлы для `build-offline`
- **compose_up_offline** — merge-файлы для `up-offline`
- **compose_up_offline_lab** — то же + `docker-compose.lab.yml` (флаг `up-offline --lab`)

Если `compose_up_offline` не задан, CLI использует `compose_build`.

### Home lab (`--lab`)

1. Создайте `docker-compose.lab.yml` в корне проекта (порты, volumes, traefik и т.д.).
2. Укажите `compose_up_offline_lab` — порядок `-f` файлов для `docker compose up`.
3. Запуск: `offline-docker up-offline -p . --lab`

Если `compose_up_offline_lab` пустой, CLI возьмёт список из `compose_up_offline` и добавит `docker-compose.lab.yml` в конец.

### Trivy (`trivy`)

Секция влияет на `download-trivy-db` и `scan-trivy-offline`:

| Поле | Назначение |
|------|------------|
| `scanner_image` | Образ Trivy (должен быть в `docker_images`) |
| `db_max_age_days` | Когда считать БД устаревшей |
| `severity` | Фильтр для scan (`HIGH,CRITICAL`) |
| `scanners` | Типы сканеров (`vuln`, `secret`, …) |

Команда scan требует позиционный аргумент `backend` или `frontend`:

```bash
offline-docker scan-trivy-offline -p . backend
offline-docker scan-trivy-offline -p . frontend myapp-frontend:custom-tag
```

Образ для scan берётся из `images.backend` / `images.frontend`, если не передан третий аргумент.
