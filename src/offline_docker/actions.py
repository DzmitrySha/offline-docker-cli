"""Shared command handlers for CLI and TUI."""

from __future__ import annotations

from typing import Any

from offline_docker import docker_cmd
from offline_docker.build import (
    build_base_offline_cmd,
    build_offline,
    down_stack,
    up_offline,
    up_online,
)
from offline_docker.context import ProjectContext
from offline_docker.discover import format_discovery_report
from offline_docker.download_debs import download_debs
from offline_docker.download_images import download_docker_images
from offline_docker.download_npm import download_npm_cache
from offline_docker.download_trivy import download_trivy_db
from offline_docker.download_wheels import download_wheels
from offline_docker.download_yarn import download_yarn_cache
from offline_docker.hooks import run_after_cache_hooks
from offline_docker.load_images import load_docker_images
from offline_docker.trivy_scan import scan_trivy_offline
from offline_docker.validate import validate_offline_cache

# Canonical action names (CLI 2.x).
PROJECT_ACTIONS = frozenset(
    {
        "discover",
        "cache",
        "cache-wheels",
        "cache-debs",
        "cache-npm",
        "cache-yarn",
        "cache-images",
        "cache-trivy",
        "cache-check",
        "cache-load",
        "build",
        "build-base",
        "up",
        "up-online",
        "down",
        "scan",
    }
)

DOCKER_ACTIONS = frozenset(PROJECT_ACTIONS - {"discover", "cache-check"})


def resolve_action(name: str) -> str:
    """Validate and return a canonical action name."""
    if name not in PROJECT_ACTIONS:
        raise ValueError(f"Unknown action: {name}")
    return name


def download_offline_cache(ctx: ProjectContext) -> None:
    print("========================================")
    print(" cache (полный набор)")
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
    run_after_cache_hooks(ctx)
    print("=== offline-cache готов ===")
    print(docker_cmd.dir_size_human(ctx.offline_cache))


def run_action(name: str, ctx: ProjectContext, **opts: Any) -> None:
    """Run a project-scoped action by name.

    Supported opts (by action):
      build / build-base / up-online: no_cache
      build: targets (list[str] | None)
      up: lab, no_build, no_deps, services, no_cache, online
      down: lab, online, services
      scan: target, image (scanner defaults to trivy)
    """
    canon = resolve_action(name)

    if canon == "discover":
        print(format_discovery_report(ctx.config))
        return
    if canon == "cache-wheels":
        download_wheels(ctx)
        return
    if canon == "cache-debs":
        download_debs(ctx)
        return
    if canon == "cache-npm":
        download_npm_cache(ctx)
        return
    if canon == "cache-yarn":
        download_yarn_cache(ctx)
        return
    if canon == "cache-images":
        download_docker_images(ctx)
        return
    if canon == "cache-trivy":
        download_trivy_db(ctx)
        return
    if canon == "cache":
        download_offline_cache(ctx)
        return
    if canon == "cache-check":
        validate_offline_cache(ctx)
        return
    if canon == "cache-load":
        load_docker_images(ctx)
        return
    if canon == "build-base":
        build_base_offline_cmd(ctx, no_cache=bool(opts.get("no_cache")))
        return
    if canon == "build":
        targets = opts.get("targets")
        build_offline(
            ctx,
            list(targets) if targets else None,
            no_cache=bool(opts.get("no_cache")),
        )
        return
    if canon == "up-online":
        up_online(ctx, no_cache=bool(opts.get("no_cache")))
        return
    if canon == "up":
        if opts.get("online"):
            up_online(ctx, no_cache=bool(opts.get("no_cache")))
            return
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
    if canon == "down":
        services = opts.get("services")
        down_stack(
            ctx,
            lab=bool(opts.get("lab")),
            online=bool(opts.get("online")),
            services=list(services) if services else None,
        )
        return
    if canon == "scan":
        target = opts.get("target")
        if target not in ("backend", "frontend"):
            raise ValueError("scan requires target=backend|frontend")
        # Future: opts.get("scanner", "trivy")
        scan_trivy_offline(ctx, target, opts.get("image"))
        return

    raise ValueError(f"Unhandled action: {canon}")
