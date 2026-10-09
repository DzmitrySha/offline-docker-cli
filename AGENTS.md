# AGENTS.md — offline-docker-cli

CLI (`offdock`) для offline-cache, сборки и выката Docker-проектов NeuroAI на машине разработчика / offline VM.

## Роль

Инфраструктурный инструмент lab/offline-контура. **Не** продуктовый app.  
Работает с `--project` / `-p` на целевой репозиторий; сам конфиг проектов не хранит.

## Связь с каноном

Эталон использования: `ai-template` + `docs/OFFLINE_CI.md` / `.offline-docker.json` в apps.  
Offline-рецепты apps **не** `include` в root `.gitlab-ci.yml` (prod tag-pipeline отдельно).

## Правила агента

1. Русский в ответах.
2. Не ломать CLI API без major; см. README (breaking 2.x).
3. При правках — проверять на реальном `-p` (template / prognoz / factory).
4. Meta-контекст NeuroAI: `d:\opo\NeuroAI\all_NeuroAI\docs\PLATFORM.md`.
