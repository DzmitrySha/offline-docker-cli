# AGENTS.md — offline-docker-cli

CLI (`offdock`) для offline-cache, сборки и выката Docker-проектов NeuroAI на машине разработчика / offline VM.

## FQDN / контуры

N/A (инструмент; FQDN задаёт целевой `--project`).

## Стек

Python CLI `offdock`; конфиг берётся из целевого репо (`.offline-docker.json` и т.п.).

## Отклонения от ai-template

**Не** продуктовый app. Сам не деплоится как NeuroAI-сервис.

## GPU

N/A.

## Lab infra

Часть lab/offline-контура рядом с `traefik` / apps. Meta: `d:\opo\NeuroAI\all_NeuroAI\docs\PLATFORM.md`.

## Роль

Работает с `--project` / `-p` на целевой репозиторий; сам конфиг проектов не хранит.  
Эталон использования: `ai-template` + `docs/OFFLINE_CI.md`. Offline-рецепты apps **не** `include` в root `.gitlab-ci.yml`.

## Правила агента

1. Русский в ответах.
2. Не ломать CLI API без major; см. README (breaking 2.x).
3. При правках — проверять на реальном `-p` (template / `prognoz_np` / factory).
