# Участие

Спасибо за улучшение `offdock`. Репозиторий содержит Python CLI (`offline-docker-cli`); это CLI-инструмент, а не деплоируемый сервис.

## Окружение

- Python 3.11+ (в CI используется 3.12)
- Docker CLI (нужен для `build` / `up` / `cache load` / `scan`)
- [uv](https://docs.astral.sh/uv/)

```bash
uv sync --extra dev      # .venv с pyyaml, textual, pytest
uv run pytest -q
uv run offdock --version
uv run offdock --help
```

Не ставьте `pytest` отдельно — он входит в extra `dev`.

## Lock-файл

При любом изменении зависимостей перегенерируйте и закоммитьте lock:

```bash
uv lock
```

CI выполняет `uv sync --locked --extra dev`, поэтому устаревший `uv.lock` валит пайплайн.

## Запуск без установки

В Windows `offdock.cmd` выставляет `PYTHONPATH=src` и запускает `python -m offline_docker`:

```powershell
offdock.cmd discover -p C:\work\my-project
```

## Контракты

См. также [`AGENTS.md`](../../AGENTS.md).

- Единственный entrypoint — `offdock`; не возвращайте `offline-docker` и старые aliases подкоманд.
- CLI API может ломаться только в major-релизе.
- Версия синхронизируется в `pyproject.toml` и `src/offline_docker/__init__.py`.
- `hooks.after_cache` и `validation.critical_vendor` — контракт проекта: нельзя «проглатывать» отсутствие скрипта или critical paths.
- Проектные конфиги в CLI не храните; всё живёт в целевом репозитории.

## Проверка на реальном проекте

Перед PR прогоните изменённую команду на реальном целевом проекте:

- `offdock discover -p C:\work\my-project`
- `offdock discover -p D:\work\another-project`

## Документация

Изменение поведения отражается в обеих языковых версиях:

- `README.md` (RU) и `.github/README.md` (EN)
- `CONTRIBUTING.md` / `SECURITY.md` / `CHANGELOG.md` (EN) и `docs/ru/` (RU)

## Коммиты и pull request

- Короткий императивный заголовок с типом: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:` (как в текущей истории).
- Один PR — одна тема.
- Не коммитьте архивы (`*.rar`, `*.zip` уже в `.gitignore`) и user-level `sources.json`.
- Заполняйте шаблон PR: что изменено, зачем и как проверено.
