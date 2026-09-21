"""Universal CLI for Docker offline cache / build / scan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from offline_docker import __version__, docker_cmd
from offline_docker.actions import DOCKER_ACTIONS, run_action
from offline_docker.context import ProjectContext

_MAIN_EPILOG = """\
примеры:
  offdock configure
  offdock init -p .
  offdock discover -p .
  offdock cache -p /path/to/project
  offdock build -p .
  offdock up -p . --lab
  offdock down -p .
  offdock scan backend
  offdock scan trivy frontend
  offdock tui -p .

после pip install: offdock configure  (Enter = только offline-cache)
init: рекурсивный черновик .offline-docker.json (или .generated.json если канон есть)
конфиг целевого проекта: .offline-docker.json (шаблон: examples/offline-docker.json.example)
TUI (опционально): pip install -e ".[tui]" && offdock tui
alias: offline-docker (deprecated) → тот же CLI
подробнее: offdock <команда> --help
"""

_INIT_EPILOG = """\
примеры:
  offdock init -p .
  offdock init -p . --dry-run

выходной файл:
  нет канона -> .offline-docker.json
  есть .offline-docker.json/.yaml -> .offline-docker.generated.json (канон не трогаем)

черновик содержит секцию _init.gaps (список того, что доработать вручную).
offline-Dockerfile / compose.offline НЕ генерируются — только пути и gaps.
"""

_CACHE_EPILOG = """\
примеры:
  offdock cache                 # полный offline-cache
  offdock cache wheels
  offdock cache debs
  offdock cache npm
  offdock cache yarn
  offdock cache images
  offdock cache trivy
  offdock cache check           # validate
  offdock cache load            # *.tar → docker load
"""

_UP_EPILOG = """\
примеры:
  offdock up -p .
  offdock up -p . --lab
  offdock up -p . --online
  offdock up -p . --no-build
  offdock up -p . --no-cache
  offdock up -p . --no-deps backend
  offdock up -p . --lab frontend

режимы (взаимоисключающие --lab / --online):
  без флагов  offline-стек (compose_up_offline)
  --lab       offline + docker-compose.lab.yml
  --online    только compose_online (бывший dev-up)

--lab:
  Подключает docker-compose.lab.yml к merge-стеку.
  В проекте нужны: файл docker-compose.lab.yml и секция compose_up_offline_lab
  в .offline-docker.json (см. examples/offline-docker.json.example).
"""

_DOWN_EPILOG = """\
примеры:
  offdock down -p .
  offdock down -p . --lab
  offdock down -p . --online
  offdock down -p . backend frontend
  offdock down -p . --lab backend

тот же выбор compose-файлов, что у up / up --lab / up --online.
без --volumes (данные томов не удаляются).
"""

_SCAN_EPILOG = """\
примеры:
  offdock scan backend
  offdock scan frontend
  offdock scan trivy backend
  offdock scan trivy frontend myapp-frontend:latest

аргументы:
  [trivy]  опционально: сканер (default: trivy)
  target   обязательный: backend или frontend
  image    опционально: тег образа (default: images.backend / images.frontend из конфига)

перед сканом:
  - образ собран локально (build)
  - БД Trivy в offline-cache/trivy/ (cache trivy)
  - образ aquasec/trivy:latest (cache load)

параметры scan (severity, scanners) — секция trivy в .offline-docker.json
лог: {log_dir}/trivy-scan-<target>.log
"""

_BUILD_EPILOG = """\
примеры:
  offdock build -p .
  offdock build -p . backend
  offdock build -p . base backend frontend
  offdock build -p . --no-cache
"""

_TUI_EPILOG = """\
примеры:
  offdock tui
  offdock tui -p .

нужна optional-зависимость:
  pip install -e ".[tui]"
"""

_CACHE_SUB_TO_ACTION = {
    "wheels": "cache-wheels",
    "debs": "cache-debs",
    "npm": "cache-npm",
    "yarn": "cache-yarn",
    "images": "cache-images",
    "trivy": "cache-trivy",
    "check": "cache-check",
    "load": "cache-load",
}

# Flat deprecated command → canonical action name for run_action.
_DEPRECATED_ALIASES: dict[str, str] = {
    "download-offline-cache": "cache",
    "download-wheels": "cache-wheels",
    "download-debs": "cache-debs",
    "download-npm-cache": "cache-npm",
    "download-yarn-cache": "cache-yarn",
    "download-docker-images": "cache-images",
    "download-trivy-db": "cache-trivy",
    "validate-offline-cache": "cache-check",
    "load-docker-images": "cache-load",
    "build-offline": "build",
    "build-base-offline": "build-base",
    "up-offline": "up",
    "dev-up": "up-online",
    "scan-trivy-offline": "scan",
}


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


def _add_lab_online_group(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--lab",
        action="store_true",
        help="home lab: добавить docker-compose.lab.yml",
    )
    mode.add_argument(
        "--online",
        action="store_true",
        help="online compose (compose_online; бывший dev-up)",
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
    if hasattr(args, "online"):
        opts["online"] = args.online
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="offdock",
        description="CLI для offline-cache, офлайн-сборки Docker и Trivy-сканирования.",
        epilog=_MAIN_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    from offline_docker.configure import add_configure_parser

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

    p_cache = add_cmd(
        "cache",
        "Скачать / проверить / загрузить offline-cache",
        description="Без подкоманды — полный download. Подкоманды: wheels, debs, …",
        epilog=_CACHE_EPILOG,
    )
    cache_sub = p_cache.add_subparsers(dest="cache_cmd", required=False)
    for cname, chelp in (
        ("wheels", "Download Python wheels"),
        ("debs", "Download .deb packages"),
        ("npm", "Download npm cache"),
        ("yarn", "Download yarn cache"),
        ("images", "docker pull + save base images"),
        ("trivy", "Download Trivy vulnerability DB"),
        ("check", "Validate offline-cache completeness"),
        ("load", "docker load from offline-cache/docker"),
    ):
        cp = cache_sub.add_parser(cname, help=chelp)
        _add_project_args(cp)

    p_build = add_cmd(
        "build",
        "Offline build base/backend/frontend",
        epilog=_BUILD_EPILOG,
    )
    p_build.add_argument(
        "targets",
        nargs="*",
        default=None,
        help="base backend frontend (default: из config.build_services)",
    )
    _add_no_cache_arg(p_build)

    p_up = add_cmd(
        "up",
        "Compose up (offline / --lab / --online)",
        description="Поднять стек: offline (default), --lab или --online.",
        epilog=_UP_EPILOG,
    )
    _add_lab_online_group(p_up)
    p_up.add_argument(
        "--no-build",
        action="store_true",
        help="Не пересобирать образы (только offline/lab)",
    )
    p_up.add_argument(
        "--no-deps",
        action="store_true",
        help="Не пересоздавать зависимые сервисы (только offline/lab)",
    )
    _add_no_cache_arg(p_up)
    p_up.add_argument(
        "services",
        nargs="*",
        default=None,
        help="сервисы (default: все; игнорируется при --online)",
    )

    p_down = add_cmd(
        "down",
        "Compose down (тот же стек, что up)",
        epilog=_DOWN_EPILOG,
    )
    _add_lab_online_group(p_down)
    p_down.add_argument(
        "services",
        nargs="*",
        default=None,
        help="сервисы (default: весь стек)",
    )

    p_scan = add_cmd(
        "scan",
        "Скан образа (default: trivy)",
        description="Trivy scan образа backend или frontend (офлайн).",
        epilog=_SCAN_EPILOG,
    )
    p_scan.add_argument(
        "scanner_or_target",
        help="trivy | backend | frontend",
    )
    p_scan.add_argument(
        "target_or_image",
        nargs="?",
        default=None,
        help="target (если первый arg = scanner) или image tag",
    )
    p_scan.add_argument(
        "image",
        nargs="?",
        default=None,
        help="опциональный тег образа",
    )

    add_cmd(
        "tui",
        "Интерактивный Textual TUI (optional: pip install -e \".[tui]\")",
        description="Terminal UI поверх тех же команд offdock.",
        epilog=_TUI_EPILOG,
    )

    for old_name in _DEPRECATED_ALIASES:
        help_text = f"(deprecated) use '{_DEPRECATED_ALIASES[old_name].replace('-', ' ')}'"
        if old_name == "scan-trivy-offline":
            p = add_cmd(old_name, help_text, epilog=_SCAN_EPILOG)
            p.add_argument("target", choices=["backend", "frontend"])
            p.add_argument("image", nargs="?", default=None)
        elif old_name == "build-offline":
            p = add_cmd(old_name, help_text)
            p.add_argument("targets", nargs="*", default=None)
            _add_no_cache_arg(p)
        elif old_name == "build-base-offline":
            p = add_cmd(old_name, help_text)
            _add_no_cache_arg(p)
        elif old_name == "up-offline":
            p = add_cmd(old_name, help_text, epilog=_UP_EPILOG)
            p.add_argument("--lab", action="store_true")
            p.add_argument("--no-build", action="store_true")
            p.add_argument("--no-deps", action="store_true")
            _add_no_cache_arg(p)
            p.add_argument("services", nargs="*", default=None)
        elif old_name == "dev-up":
            p = add_cmd(old_name, help_text)
            _add_no_cache_arg(p)
        else:
            add_cmd(old_name, help_text)

    return parser


def _normalize_scan_args(args: argparse.Namespace) -> None:
    """Resolve scan trivy|backend positional forms into target/image."""
    first = args.scanner_or_target
    second = args.target_or_image
    third = args.image
    if first in ("backend", "frontend"):
        args.target = first
        args.image = second
        args.scanner = "trivy"
    elif first == "trivy":
        if second not in ("backend", "frontend"):
            raise SystemExit(
                "scan trivy: нужен target backend|frontend "
                f"(получено: {second!r})"
            )
        args.target = second
        args.image = third
        args.scanner = "trivy"
    else:
        raise SystemExit(
            f"scan: неизвестный аргумент {first!r}; "
            "ожидается trivy|backend|frontend"
        )


def _resolve_action_name(args: argparse.Namespace) -> str:
    cmd = args.command
    if cmd == "cache":
        sub = getattr(args, "cache_cmd", None)
        if not sub:
            return "cache"
        return _CACHE_SUB_TO_ACTION[sub]
    if cmd in _DEPRECATED_ALIASES:
        return _DEPRECATED_ALIASES[cmd]
    return cmd


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI argv (exposed for tests)."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        _normalize_scan_args(args)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.command == "configure":
        from offline_docker.configure import run_configure

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

    action = _resolve_action_name(args)
    if action in DOCKER_ACTIONS:
        docker_cmd.require_docker()

    ctx = _load_ctx(args)

    try:
        run_action(action, ctx, **_action_opts(args))
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
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
