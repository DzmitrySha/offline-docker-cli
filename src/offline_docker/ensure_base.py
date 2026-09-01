"""Ensure base Docker images (reuse / build)."""

from __future__ import annotations

from offline_docker import docker_cmd
from offline_docker.context import ProjectContext
from offline_docker.utils import docker_mount_path


def ensure_base_online(
    ctx: ProjectContext, image: str | None = None, *, no_cache: bool = False
) -> None:
    image = image or ctx.config.images.base
    if not no_cache and docker_cmd.image_exists(image):
        print(f">>> reuse existing base: {image}")
        return
    df = ctx.config.dockerfiles.base
    print(f">>> docker build base -> {image}")
    cmd = ["docker", "build"]
    if no_cache:
        cmd.append("--no-cache")
    cmd.extend(["-f", df, "-t", image, "."])
    docker_cmd.run(cmd, cwd=ctx.root, env={"DOCKER_BUILDKIT": "1"})


def require_base_offline(ctx: ProjectContext, image: str | None = None) -> None:
    image = image or ctx.config.images.base
    if not docker_cmd.image_exists(image):
        raise SystemExit(
            f"Ошибка: образ {image} не найден. "
            "Сначала: offline-docker build-base-offline"
        )


def build_base_offline(
    ctx: ProjectContext, image: str | None = None, *, no_cache: bool = False
) -> None:
    image = image or ctx.config.images.base
    if not no_cache and docker_cmd.image_exists(image):
        print(f">>> reuse existing base: {image}")
        return

    log_file = ctx.offline_build_log("base")
    df = ctx.config.dockerfiles.base_offline
    oc_ctx = docker_mount_path(ctx.offline_cache)
    print(f">>> docker build base -> {log_file}")
    cmd = ["docker", "build"]
    if no_cache:
        cmd.append("--no-cache")
    cmd.extend(
        [
            "-f",
            df,
            "--build-context",
            f"oc={oc_ctx}",
            "-t",
            image,
            ".",
        ]
    )
    docker_cmd.run_tee(cmd, log_file, cwd=ctx.root, env={"DOCKER_BUILDKIT": "1"})
