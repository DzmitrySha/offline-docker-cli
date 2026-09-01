"""Universal CLI for Docker offline cache / build / scan."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from offline_docker import docker_cmd
from offline_docker.build import build_base_offline_cmd, build_offline, dev_up, up_offline
from offline_docker.context import ProjectContext
from offline_docker.discover import format_discovery_report
from offline_docker.download_debs import download_debs
from offline_docker.download_images import download_docker_images
from offline_docker.download_npm import download_npm_cache
from offline_docker.download_trivy import download_trivy_db
from offline_docker.download_wheels import download_wheels
from offline_docker.load_images import load_docker_images
from offline_docker.trivy_scan import scan_trivy_offline
from offline_docker.validate import validate_offline_cache

_MAIN_EPILOG = """\
примеры:
  offline-docker discover -p .
  offline-docker download-offline-cache -p /path/to/project
  offline-docker build-offline -p .
  offline-docker up-offline -p . --lab
  offline-docker scan-trivy-offline -p . backend

конфиг целевого проекта: .offline-docker.json (шаблон: examples/offline-docker.json.example)
подробнее: offline-docker <команда> --help
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


def _download_offline_cache(ctx: ProjectContext) -> None:
    print("========================================")
    print(" download-offline-cache (полный набор)")
    print(f" Project: {ctx.root}")
    print("========================================")
    print()
    download_debs(ctx)
    print()
    download_wheels(ctx)
    print()
    download_npm_cache(ctx)
    print()
    download_docker_images(ctx)
    print()
    download_trivy_db(ctx)
    print()
    print("=== offline-cache готов ===")
    print(docker_cmd.dir_size_human(ctx.offline_cache))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="offline-docker",
        description="CLI для offline-cache, офлайн-сборки Docker и Trivy-сканирования.",
        epilog=_MAIN_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

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

    add_cmd("discover", "Показать обнаруженные зависимости проекта")

    for name, help_text in (
        ("download-wheels", "Download Python wheels"),
        ("download-debs", "Download .deb packages"),
        ("download-npm-cache", "Download npm cache"),
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

    args = parser.parse_args(argv)
    docker_cmd.require_docker()
    ctx = _load_ctx(args)

    handlers: dict[str, object] = {
        "discover": lambda: print(format_discovery_report(ctx.config)),
        "download-wheels": lambda: download_wheels(ctx),
        "download-debs": lambda: download_debs(ctx),
        "download-npm-cache": lambda: download_npm_cache(ctx),
        "download-docker-images": lambda: download_docker_images(ctx),
        "download-trivy-db": lambda: download_trivy_db(ctx),
        "download-offline-cache": lambda: _download_offline_cache(ctx),
        "validate-offline-cache": lambda: validate_offline_cache(ctx),
        "load-docker-images": lambda: load_docker_images(ctx),
        "build-base-offline": lambda: build_base_offline_cmd(ctx, no_cache=args.no_cache),
        "build-offline": lambda: build_offline(
            ctx,
            list(args.targets) if args.targets else None,
            no_cache=args.no_cache,
        ),
        "dev-up": lambda: dev_up(ctx, no_cache=args.no_cache),
        "up-offline": lambda: up_offline(
            ctx,
            lab=args.lab,
            no_build=args.no_build,
            no_deps=args.no_deps,
            no_cache=args.no_cache,
            services=list(args.services) if args.services else None,
        ),
        "scan-trivy-offline": lambda: scan_trivy_offline(ctx, args.target, args.image),
    }

    try:
        handlers[args.command]()
    except docker_cmd.CommandError as exc:
        print(str(exc), file=sys.stderr)
        return exc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
