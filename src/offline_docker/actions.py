"""Shared command handlers for CLI and TUI."""

from __future__ import annotations

from typing import Any

from offline_docker import docker_cmd
from offline_docker.build import build_base_offline_cmd, build_offline, dev_up, up_offline
from offline_docker.context import ProjectContext
from offline_docker.discover import format_discovery_report
from offline_docker.download_debs import download_debs
from offline_docker.download_images import download_docker_images
from offline_docker.download_npm import download_npm_cache
from offline_docker.download_trivy import download_trivy_db
from offline_docker.download_wheels import download_wheels
from offline_docker.download_yarn import download_yarn_cache
from offline_docker.load_images import load_docker_images
from offline_docker.trivy_scan import scan_trivy_offline
from offline_docker.validate import validate_offline_cache

# Actions that need a ProjectContext (not configure/init).
PROJECT_ACTIONS = frozenset(
    {
        "discover",
        "download-wheels",
        "download-debs",
        "download-npm-cache",
        "download-yarn-cache",
        "download-docker-images",
        "download-trivy-db",
        "download-offline-cache",
        "validate-offline-cache",
        "load-docker-images",
        "build-base-offline",
        "build-offline",
        "dev-up",
        "up-offline",
        "scan-trivy-offline",
    }
)

# Subset that shell out to docker / compose.
DOCKER_ACTIONS = frozenset(PROJECT_ACTIONS - {"discover", "validate-offline-cache"})


def download_offline_cache(ctx: ProjectContext) -> None:
    print("========================================")
    print(" download-offline-cache (полный набор)")
    print(f" Project: {ctx.root}")
    print("========================================")
    print()
    from offline_docker.sync_cache import maybe_materialize

    maybe_materialize(ctx)
    download_debs(ctx)
    print()
    download_wheels(ctx)
    print()
    download_npm_cache(ctx)
    print()
    download_yarn_cache(ctx)
    print()
    download_docker_images(ctx)
    print()
    download_trivy_db(ctx)
    print()
    print("=== offline-cache готов ===")
    print(docker_cmd.dir_size_human(ctx.offline_cache))


def run_action(name: str, ctx: ProjectContext, **opts: Any) -> None:
    """Run a project-scoped action by name.

    Supported opts (by action):
      build-base-offline / build-offline / dev-up / up-offline: no_cache
      build-offline: targets (list[str] | None)
      up-offline: lab, no_build, no_deps, services
      scan-trivy-offline: target, image
    """
    if name not in PROJECT_ACTIONS:
        raise ValueError(f"Unknown action: {name}")

    if name == "discover":
        print(format_discovery_report(ctx.config))
        return
    if name == "download-wheels":
        download_wheels(ctx)
        return
    if name == "download-debs":
        download_debs(ctx)
        return
    if name == "download-npm-cache":
        download_npm_cache(ctx)
        return
    if name == "download-yarn-cache":
        download_yarn_cache(ctx)
        return
    if name == "download-docker-images":
        download_docker_images(ctx)
        return
    if name == "download-trivy-db":
        download_trivy_db(ctx)
        return
    if name == "download-offline-cache":
        download_offline_cache(ctx)
        return
    if name == "validate-offline-cache":
        validate_offline_cache(ctx)
        return
    if name == "load-docker-images":
        load_docker_images(ctx)
        return
    if name == "build-base-offline":
        build_base_offline_cmd(ctx, no_cache=bool(opts.get("no_cache")))
        return
    if name == "build-offline":
        targets = opts.get("targets")
        build_offline(
            ctx,
            list(targets) if targets else None,
            no_cache=bool(opts.get("no_cache")),
        )
        return
    if name == "dev-up":
        dev_up(ctx, no_cache=bool(opts.get("no_cache")))
        return
    if name == "up-offline":
        services = opts.get("services")
        up_offline(
            ctx,
            lab=bool(opts.get("lab")),
            no_build=bool(opts.get("no_build")),
            no_deps=bool(opts.get("no_deps")),
            no_cache=bool(opts.get("no_cache")),
            services=list(services) if services else None,
        )
        return
    if name == "scan-trivy-offline":
        target = opts.get("target")
        if target not in ("backend", "frontend"):
            raise ValueError("scan-trivy-offline requires target=backend|frontend")
        scan_trivy_offline(ctx, target, opts.get("image"))
        return

    raise ValueError(f"Unhandled action: {name}")
