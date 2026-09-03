# Шаблон `.offline-docker.json`

Универсальный пример для любого проекта NeuroAI (backend + frontend, slim CUDA base, offline-cache).

## Установка в проект

```bash
# Вариант A: авто-черновик (рекурсивный scan + gaps)
offline-docker init -p /path/to/your-project

# Вариант B: ручной шаблон
cp examples/offline-docker.json.example /path/to/your-project/.offline-docker.json
```

Если `.offline-docker.json` уже есть, `init` пишет `.offline-docker.generated.json` и не затирает канон.

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
| `build_services` | имена сервисов для `build-offline`: `base` (отдельная сборка) и любые ключи из merge compose |

## Проверка

```bash
offline-docker discover -p /path/to/your-project
```

## Секции конфига

- **compose_build** — merge-файлы для `build-offline`
- **compose_up_offline** — merge-файлы для `up-offline`
- **build_services** — список для `build-offline` без аргументов: `base` + имена сервисов из compose (не только backend/frontend)
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

### Package sources (`cache`) — опционально

Секция **не обязательна** в project-конфиге. По умолчанию источники настраиваются один раз на машину:

```bash
offline-docker configure
```

Если нужна project-specific цепочка (перекрывает user-config), добавьте нейтральный блок с **пустыми** URL или своими значениями:

```json
"cache": {
  "sources": [
    { "name": "local", "type": "filesystem", "enabled": true },
    {
      "name": "proget",
      "type": "proget",
      "url": "",
      "feeds": { "pypi": "", "npm": "", "deb": "" },
      "enabled": false
    },
    {
      "name": "nexus",
      "type": "nexus",
      "url": "",
      "repos": { "pypi": "", "npm": "" },
      "enabled": false
    }
  ],
  "resolve": {
    "order": ["local"],
    "fill_local": true,
    "on_miss": "fail"
  }
}
```

Пустые URL / `enabled: false` = только offline-cache. Корпоративные адреса в этот example **не** вносятся — см. `offline-docker configure --help`.
