"""Offline build orchestration."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from offline_docker import docker_cmd
from offline_docker.context import ProjectContext
from offline_docker.download_npm import download_npm_cache
from offline_docker.download_wheels import download_wheels
from offline_docker.ensure_base import build_base_offline, require_base_offline
from offline_docker.load_images import load_docker_images
from offline_docker.validate import validate_offline_cache


def _stamp_ui_project_label(image: str, project: str) -> None:
    print(f">>> stamp UI label {image} -> com.docker.compose.project={project}")
    with tempfile.TemporaryDirectory(prefix="od-stamp-") as tmp:
        df = Path(tmp) / "Dockerfile"
        df.write_text(
            f"FROM {image}\nLABEL com.docker.compose.project={project}\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["docker", "build", "-t", image, "-f", str(df), tmp],
            check=True,
        )


def build_base_offline_cmd(ctx: ProjectContext) -> None:
    image = os.environ.get("IMAGE", ctx.config.images.base)
    ctx.set_offline_cache_env()

    print("=== build-base-offline ===")
    print(f"Project:       {ctx.root}")
    print(f"Offline cache: {ctx.offline_cache}")
    print(f"Image:         {image}")
    print()

    download_wheels(ctx)
    validate_offline_cache(ctx)
    load_docker_images(ctx)
    build_base_offline(ctx, image)

    print()
    print(f"=== Готово: {image} ===")


def build_offline(ctx: ProjectContext, targets: list[str] | None = None) -> None:
    if not targets:
        targets = list(ctx.config.build_services)

    ctx.set_offline_cache_env()
    compose_args = ctx.config.compose_build_file_args()

    print("=== build-offline ===")
    print(f"Project:       {ctx.root}")
    print(f"Offline cache: {ctx.offline_cache}")
    print(f"Compose:       {' '.join(compose_args)}")
    print(f"Логи:          {ctx.log_dir}")
    print(f"Сервисы:       {' '.join(targets)}")
    print()

    download_wheels(ctx)
    download_npm_cache(ctx)
    validate_offline_cache(ctx)
    load_docker_images(ctx)

    compose_targets: list[str] = []
    for svc in targets:
        if svc == "base":
            build_base_offline(ctx)
        elif svc in ("backend", "frontend"):
            compose_targets.append(svc)
        else:
            raise SystemExit(
                f"Неизвестный сервис: {svc} (допустимо: base, backend, frontend)"
            )

    for svc in compose_targets:
        if svc == "backend":
            require_base_offline(ctx)
        log_file = ctx.offline_build_log(svc)
        print(f">>> compose build {svc} -> {log_file}")
        docker_cmd.run_tee(
            [
                "docker",
                "compose",
                *compose_args,
                "build",
                svc,
            ],
            log_file,
            cwd=ctx.root,
            env={"DOCKER_BUILDKIT": "1"},
        )

    image_map = {
        "backend": os.environ.get("BACKEND_IMAGE", ctx.config.images.backend),
        "frontend": os.environ.get("FRONTEND_IMAGE", ctx.config.images.frontend),
    }
    for svc in compose_targets:
        _stamp_ui_project_label(image_map[svc], ctx.config.app_name)

    print()
    print(f"=== Готово. Логи: {ctx.log_dir}/offline-build-*.log ===")


def dev_up(ctx: ProjectContext) -> None:
    from offline_docker.ensure_base import ensure_base_online

    compose = ctx.config.compose_online
    print("=== dev-up ===")
    print(f"Project: {ctx.root}")
    print(f"Compose: {compose}")
    print()

    ensure_base_online(ctx)
    docker_cmd.run(
        ["docker", "compose", "-f", compose, "build"],
        cwd=ctx.root,
        env={"DOCKER_BUILDKIT": "1"},
    )
    docker_cmd.run(
        ["docker", "compose", "-f", compose, "up", "-d"],
        cwd=ctx.root,
        env={"DOCKER_BUILDKIT": "1"},
    )
    print()
    print("=== dev-up: контейнеры подняты ===")


def _ensure_traefik_network() -> None:
    subprocess.run(
        ["docker", "network", "create", "traefik_proxy"],
        check=False,
        capture_output=True,
    )


def up_offline(
    ctx: ProjectContext,
    *,
    lab: bool = False,
    no_build: bool = False,
    no_deps: bool = False,
    services: list[str] | None = None,
) -> None:
    ctx.set_offline_cache_env()
    compose_args = ctx.config.compose_up_file_args(lab=lab)

    print("=== up-offline ===")
    print(f"Project: {ctx.root}")
    print(f"Offline cache: {ctx.offline_cache}")
    print(f"Compose:       {' '.join(compose_args)}")
    if lab:
        print("Lab:           docker-compose.lab.yml")
    print()

    _ensure_traefik_network()

    cmd = ["docker", "compose", *compose_args, "up", "-d"]
    if no_build:
        cmd.append("--no-build")
    if no_deps:
        cmd.append("--no-deps")
    if services:
        cmd.extend(services)

    docker_cmd.run(cmd, cwd=ctx.root, env={"DOCKER_BUILDKIT": "1"})
    print()
    print("=== up-offline: контейнеры подняты ===")
