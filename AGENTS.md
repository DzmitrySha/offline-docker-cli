# AGENTS.md — offline-docker-cli

CLI (`offdock`) для offline-cache, сборки и выката Docker-проектов на машине разработчика / offline VM.

## FQDN / контуры

N/A (инструмент; FQDN задаёт целевой `--project`).

## Стек

Python CLI `offdock`; конфиг берётся из целевого репо (`.offline-docker.json` и т.п.).

## Отклонения от шаблонного app

**Не** продуктовый app. Сам не деплоится как сервис. Работает с `--project` / `-p`; конфиг проектов не хранит.

## GPU

N/A.

## Lab infra

Часть lab/offline-контура рядом с `traefik` / apps.

## Связь с каноном

Эталон: `docs/OFFLINE_CI.md` + `.offline-docker.json` в целевом app.  
Offline-рецепты apps **не** `include` в root `.gitlab-ci.yml` (prod tag-pipeline отдельно).

Проектные хуки: `hooks.after_cache` (скрипты после cache / перед build); проверка — `validate.critical_vendor`.

## Правила агента

1. Русский в ответах.
2. Не ломать CLI API без major; см. README (breaking 2.x). Entrypoint только `offdock`.
3. При правках — проверять на реальном `-p` (`..\my-project`).
4. Версия синхронно в `pyproject.toml` и `src/offline_docker/__init__.py`.
5. Хуки/vendor — контракт проекта; не «проглатывать» отсутствие скрипта или critical paths.
