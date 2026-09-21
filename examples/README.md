# Шаблон `.offline-docker.json`

Универсальный пример для любого проекта NeuroAI (backend + frontend, slim CUDA base, offline-cache).

## Установка в проект

```bash
# Вариант A: авто-черновик (рекурсивный scan + gaps)
offdock init -p /path/to/your-project

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
| `build_services` | имена сервисов для `build`: `base` (отдельная сборка) и любые ключи из merge compose |

## Проверка

```bash
offdock discover -p /path/to/your-project
```

## Секции конфига

- **compose_build** — merge-файлы для `build`
- **compose_up_offline** — merge-файлы для `up`
- **build_services** — список для `build` без аргументов: `base` + имена сервисов из compose (не только backend/frontend)
- **compose_up_offline_lab** — то же + `docker-compose.lab.yml` (флаг `up --lab`)

Если `compose_up_offline` не задан, CLI использует `compose_build`.

### Home lab (`--lab`)

1. Создайте `docker-compose.lab.yml` в корне проекта (порты, volumes, traefik и т.д.).
2. Укажите `compose_up_offline_lab` — порядок `-f` файлов для `docker compose up`.
3. Запуск: `offdock up -p . --lab`

Если `compose_up_offline_lab` пустой, CLI возьмёт список из `compose_up_offline` и добавит `docker-compose.lab.yml` в конец.

### Trivy (`trivy`)

Секция влияет на `cache trivy` и `scan` / `scan trivy`:

| Поле | Назначение |
|------|------------|
| `scanner_image` | Образ Trivy (должен быть в `docker_images`) |
| `db_max_age_days` | Когда считать БД устаревшей |
| `severity` | Фильтр для scan (`HIGH,CRITICAL`) |
| `scanners` | Типы сканеров (`vuln`, `secret`, …) |

Команда scan требует target `backend` или `frontend`:

```bash
offdock scan backend
offdock scan trivy frontend myapp-frontend:custom-tag
```

Образ для scan берётся из `images.backend` / `images.frontend`, если не передан тег.

### Package sources (`cache`) — опционально

Секция **не обязательна** в project-конфиге. По умолчанию источники настраиваются один раз на машину:

```bash
offdock configure
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

Пустые URL / `enabled: false` = только offline-cache. Корпоративные адреса в этот example **не** вносятся — см. `offdock configure --help`.
