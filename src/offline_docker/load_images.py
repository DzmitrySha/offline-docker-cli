"""Load Docker images from offline-cache/docker/*.tar."""

from __future__ import annotations

from offline_docker import docker_cmd
from offline_docker.context import ProjectContext


def load_docker_images(ctx: ProjectContext) -> None:
    print("=== load-docker-images ===")
    print(f"Каталог: {ctx.docker_cache_dir}")
    print()

    if not ctx.docker_cache_dir.is_dir():
        print(
            f"WARN: каталог {ctx.docker_cache_dir} не найден - пропуск",
            flush=True,
        )
        return

    tars = sorted(ctx.docker_cache_dir.glob("*.tar"))
    if not tars:
        print(
            f"WARN: нет .tar в {ctx.docker_cache_dir} - выполните download-docker-images",
            flush=True,
        )
        return

    for tar_path in tars:
        print(f">>> load {tar_path.name}")
        docker_cmd.run(["docker", "load", "-i", str(tar_path)])

    print()
    print(f"=== Готово: загружено {len(tars)} образов ===")
