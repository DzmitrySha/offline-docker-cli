"""Pull and save Docker images into offline-cache/docker."""

from __future__ import annotations

from offline_docker import docker_cmd
from offline_docker.context import ProjectContext


def download_docker_images(ctx: ProjectContext) -> None:
    ctx.ensure_offline_dirs()
    print("=== download-docker-images ===")
    print(f"Каталог: {ctx.docker_cache_dir}")
    print()

    for image in ctx.config.docker_images:
        safe_name = image.replace("/", "_").replace(":", "-")
        tar_path = ctx.docker_cache_dir / f"{safe_name}.tar"
        print(f">>> pull {image}")
        docker_cmd.run(["docker", "pull", image])
        print(f">>> save -> {tar_path}")
        docker_cmd.run(["docker", "save", "-o", str(tar_path), image])
        print(docker_cmd.dir_size_human(tar_path))
        print()

    tar_count = len(list(ctx.docker_cache_dir.glob("*.tar")))
    print(f"=== Готово: {tar_count} tar-файлов ===")
