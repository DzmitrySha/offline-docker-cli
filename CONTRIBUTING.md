# Contributing

Thanks for improving `offdock`. This repository ships a Python CLI (`offline-docker-cli`); it is a CLI tool, not a deployable service.

## Environment

- Python 3.11+ (3.12 is used in CI)
- Docker CLI (needed for `build` / `up` / `cache load` / `scan`)
- [uv](https://docs.astral.sh/uv/)

```bash
uv sync --extra dev      # .venv with pyyaml, textual, pytest
uv run pytest -q
uv run offdock --version
uv run offdock --help
```

Do not install `pytest` ad hoc — it is part of the `dev` extra.

## Lockfile

Whenever dependencies change, regenerate and commit the lock:

```bash
uv lock
```

CI runs `uv sync --locked --extra dev`, so a stale `uv.lock` fails the pipeline.

## Running without installing

On Windows, `offdock.cmd` sets `PYTHONPATH=src` and runs `python -m offline_docker`:

```powershell
offdock.cmd discover -p C:\work\my-project
```

## Contracts

See also [`AGENTS.md`](AGENTS.md).

- The only entrypoint is `offdock`; do not reintroduce `offline-docker` or old subcommand aliases.
- The CLI API may break only in a major release.
- Keep the version in sync in `pyproject.toml` and `src/offline_docker/__init__.py`.
- `hooks.after_cache` and `validation.critical_vendor` are project contracts: never swallow a missing script or missing critical paths.
- Do not store project-specific configs inside the CLI; everything lives in the target repository.

## Verification on a real project

Before opening a PR, run the changed command against a real target:

- `offdock discover -p C:\work\my-project`
- `offdock discover -p D:\work\another-project`

## Documentation

Behavior changes must be reflected in both language versions:

- `README.md` (RU) and `.github/README.md` (EN)
- `CONTRIBUTING.md` / `SECURITY.md` / `CHANGELOG.md` (EN) and `docs/ru/` (RU)

## Commits and pull requests

- Short imperative subject with a type: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:` (matching the existing history).
- One PR — one topic.
- Do not commit archives (`*.rar`, `*.zip` are already in `.gitignore`) or a user-level `sources.json`.
- Fill in the PR template: what changed, why, and how it was verified.
