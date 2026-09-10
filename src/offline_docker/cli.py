"""Universal CLI for Docker offline cache / build / scan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from offline_docker import docker_cmd
from offline_docker.actions import PROJECT_ACTIONS, run_action
from offline_docker.context import ProjectContext

_MAIN_EPILOG = """\
примеры:
  offline-docker configure
  offline-docker init -p .
  offline-docker discover -p .
  offline-docker download-offline-cache -p /path/to/project
  offline-docker build-offline -p .
  offline-docker up-offline -p . --lab
  offline-docker scan-trivy-offline -p . backend
  offline-docker tui -p .

после pip install: offline-docker configure  (Enter = только offline-cache)
init: рекурсивный черновик .offline-docker.json (или .generated.json если канон есть)
конфиг целевого проекта: .offline-docker.json (шаблон: examples/offline-docker.json.example)
TUI (опционально): pip install -e ".[tui]" && offline-docker tui
подробнее: offline-docker <команда> --help
"""

_INIT_EPILOG = """\
примеры:
  offline-docker init -p .
  offline-docker init -p . --dry-run

выходной файл:
  нет канона -> .offline-docker.json
  есть .offline-docker.json/.yaml -> .offline-docker.generated.json (канон не трогаем)

черновик содержит секцию _init.gaps (список того, что доработать вручную).
offline-Dockerfile / compose.offline НЕ генерируются — только пути и gaps.
"""

_UP_OFFLINE_EPILOG = """\
примеры:
  offline-docker up-offline -p .
  offline-docker up-offline -p . --lab
  offline-docker up-offline -p . --no-build
  offline-docker up-offline -p . --no-cache
  offline-docker up-offline -p . --no-deps backend
  offline-docker up-offline -p . --lab frontend

--lab (home lab):
  Подключает docker-compose.lab.yml к merge-стеку.
  В проекте нужны: файл docker-compose.lab.yml и секция compose_up_offline_lab
  в .offline-docker.json (см. examples/offline-docker.json.example).
  Если compose_up_offline_lab не задан, CLI добавит docker-compose.lab.yml
  к списку из compose_up_offline.
"""

_SCAN_TRIVY_EPILOG = """\
примеры:
  offline-docker scan-trivy-offline -p . backend
  offline-docker scan-trivy-offline -p . frontend
  offline-docker scan-trivy-offline -p . backend myapp-backend:latest

аргументы:
  target   обязательный: backend или frontend
  image    опционально: тег образа (default: images.backend / images.frontend из конфига)

перед сканом:
  - образ собран локально (build-offline)
  - БД Trivy в offline-cache/trivy/ (download-trivy-db)
  - образ aquasec/trivy:latest (load-docker-images)

параметры scan (severity, scanners) — секция trivy в .offline-docker.json
лог: {log_dir}/trivy-scan-<target>.log
"""

_BUILD_OFFLINE_EPILOG = """\
примеры:
  offline-docker build-offline -p .
  offline-docker build-offline -p . backend
  offline-docker build-offline -p . base backend frontend
  offline-docker build-offline -p . --no-cache
"""

_TUI_EPILOG = """\
примеры:
  offline-docker tui
  offline-docker tui -p .

нужна optional-зависимость:
  pip install -e ".[tui]"
"""


def _add_no_cache_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Собрать без кэша слоёв Docker (docker build/compose build --no-cache)",
    )


def _add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        default=None,
        help="Путь к корню проекта (default: текущий каталог)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Путь к .offline-docker.json / .yaml (default: в корне проекта)",
    )


def _resolve_project_path(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    return Path.cwd()


def _load_ctx(args: argparse.Namespace) -> ProjectContext:
    root = _resolve_project_path(args.project)
    return ProjectContext.load(
        root,
        config_file=args.config,
    )


def _action_opts(args: argparse.Namespace) -> dict:
    opts: dict = {}
    if hasattr(args, "no_cache"):
        opts["no_cache"] = args.no_cache
    if hasattr(args, "targets"):
        opts["targets"] = list(args.targets) if args.targets else None
    if hasattr(args, "lab"):
        opts["lab"] = args.lab
    if hasattr(args, "no_build"):
        opts["no_build"] = args.no_build
    if hasattr(args, "no_deps"):
        opts["no_deps"] = args.no_deps
    if hasattr(args, "services"):
        opts["services"] = list(args.services) if args.services else None
    if hasattr(args, "target"):
        opts["target"] = args.target
    if hasattr(args, "image"):
        opts["image"] = args.image
    return opts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="offline-docker",
        description="CLI для offline-cache, офлайн-сборки Docker и Trivy-сканирования.",
        epilog=_MAIN_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    from offline_docker.configure import add_configure_parser, run_configure

    add_configure_parser(sub)

    def add_cmd(
        name: str,
        help_text: str,
        *,
        description: str | None = None,
        epilog: str | None = None,
    ) -> argparse.ArgumentParser:
        p = sub.add_parser(
            name,
            help=help_text,
            description=description or help_text,
            epilog=epilog,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        _add_project_args(p)
        return p

    p_init = add_cmd(
        "init",
        "Рекурсивный scan → черновик .offline-docker.json",
        description=(
            "Рекурсивно ищет compose/Dockerfile/python/frontend, "
            "пишет черновик конфига и список Missing/gaps."
        ),
        epilog=_INIT_EPILOG,
    )
    p_init.add_argument(
        "--dry-run",
        action="store_true",
        help="Только отчёт, без записи файла",
    )

    add_cmd("discover", "Показать обнаруженные зависимости проекта")

    for name, help_text in (
        ("download-wheels", "Download Python wheels"),
        ("download-debs", "Download .deb packages"),
        ("download-npm-cache", "Download npm cache"),
        ("download-yarn-cache", "Download yarn cache (if *Dockerfile.offline uses source=yarn)"),
        ("download-docker-images", "docker pull + save base images"),
        ("download-trivy-db", "Download Trivy vulnerability DB"),
        ("download-offline-cache", "Run all download-* commands"),
        ("validate-offline-cache", "Validate offline-cache completeness"),
        ("load-docker-images", "docker load from offline-cache/docker"),
    ):
        add_cmd(name, help_text)

    p_build_base = add_cmd("build-base-offline", "Build base offline image")
    _add_no_cache_arg(p_build_base)

    p_dev_up = add_cmd("dev-up", "Ensure base, compose build, up")
    _add_no_cache_arg(p_dev_up)

    p_build = add_cmd(
        "build-offline",
        "Offline build base/backend/frontend",
        epilog=_BUILD_OFFLINE_EPILOG,
    )
    p_build.add_argument(
        "targets",
        nargs="*",
        default=None,
        help="base backend frontend (default: из config.build_services)",
    )
    _add_no_cache_arg(p_build)

    p_up = add_cmd(
        "up-offline",
        "Compose up offline stack (merge online+offline)",
        description="Поднять offline-стек (merge compose_up_offline из конфига).",
        epilog=_UP_OFFLINE_EPILOG,
    )
    p_up.add_argument(
        "--lab",
        action="store_true",
        help="home lab: добавить docker-compose.lab.yml (см. compose_up_offline_lab в конфиге)",
    )
    p_up.add_argument(
        "--no-build",
        action="store_true",
        help="Не пересобирать образы (deploy уже собранных)",
    )
    p_up.add_argument(
        "--no-deps",
        action="store_true",
        help="Не пересоздавать зависимые сервисы",
    )
    _add_no_cache_arg(p_up)
    p_up.add_argument(
        "services",
        nargs="*",
        default=None,
        help="backend frontend (default: все сервисы из compose)",
    )

    p_scan = add_cmd(
        "scan-trivy-offline",
        "Trivy scan backend/frontend image",
        description="Trivy scan образа backend или frontend (офлайн, --skip-db-update).",
        epilog=_SCAN_TRIVY_EPILOG,
    )
    p_scan.add_argument(
        "target",
        choices=["backend", "frontend"],
        help="обязательный: backend или frontend",
    )
    p_scan.add_argument(
        "image",
        nargs="?",
        default=None,
        help="опционально: тег образа (default: images.<target> из конфига)",
    )

    add_cmd(
        "tui",
        "Интерактивный Textual TUI (optional: pip install -e \".[tui]\")",
        description="Terminal UI поверх тех же команд offline-docker.",
        epilog=_TUI_EPILOG,
    )

    args = parser.parse_args(argv)

    if args.command == "configure":
        run_configure(args)
        return 0

    if args.command == "init":
        from offline_docker.init_cmd import run_init

        run_init(_resolve_project_path(args.project), dry_run=args.dry_run)
        return 0

    if args.command == "tui":
        try:
            import textual  # noqa: F401
            from offline_docker.tui import run_tui
        except ImportError:
            print(
                'TUI требует Textual. Установите: pip install -e ".[tui]"',
                file=sys.stderr,
            )
            return 1
        return run_tui(
            project=_resolve_project_path(args.project),
            config_file=args.config,
        )

    if args.command in PROJECT_ACTIONS:
        docker_cmd.require_docker()

    ctx = _load_ctx(args)

    try:
        run_action(args.command, ctx, **_action_opts(args))
    except docker_cmd.CommandError as exc:
        print(str(exc), file=sys.stderr)
        return exc.returncode
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
