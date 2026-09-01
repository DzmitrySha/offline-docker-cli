"""Download Trivy vulnerability DB into offline-cache/trivy."""

from __future__ import annotations

import time

from offline_docker import docker_cmd
from offline_docker.context import ProjectContext
from offline_docker.utils import docker_mount_path


def trivy_db_stale(ctx: ProjectContext) -> bool:
    """True if DB is missing or older than configured max age."""
    cache = ctx.trivy_cache_dir
    ts_file = cache / ".trivy-db.timestamp"
    max_age = ctx.config.trivy.db_max_age_days * 86400

    if not cache.is_dir():
        return True

    others = [
        p
        for p in cache.rglob("*")
        if p.is_file() and p.name != ".trivy-db.timestamp"
    ]
    if not others:
        return True

    if not ts_file.is_file():
        return True

    try:
        stamp = int(ts_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return True

    return (time.time() - stamp) > max_age


def ensure_trivy_image(ctx: ProjectContext) -> None:
    image = ctx.config.trivy.scanner_image
    if docker_cmd.image_exists(image):
        return
    from offline_docker.load_images import load_docker_images

    print(f"Образ {image} не найден — load-docker-images")
    load_docker_images(ctx)
    if not docker_cmd.image_exists(image):
        raise SystemExit(
            f"ERROR: образ {image} недоступен. Выполните download-docker-images"
        )


def download_trivy_db(ctx: ProjectContext) -> None:
    ctx.ensure_offline_dirs()
    if not trivy_db_stale(ctx):
        print(
            f"=== download-trivy-db: БД актуальна (моложе {ctx.config.trivy.db_max_age_days} дн.) ==="
        )
        print(docker_cmd.dir_size_human(ctx.trivy_cache_dir))
        return

    print("=== download-trivy-db ===")
    print(f"Каталог:  {ctx.trivy_cache_dir}")
    print(f"Образ:    {ctx.config.trivy.scanner_image}")
    print()

    ensure_trivy_image(ctx)
    cache_docker = docker_mount_path(ctx.trivy_cache_dir)

    docker_cmd.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{cache_docker}:/root/.cache/trivy",
            ctx.config.trivy.scanner_image,
            "image",
            "--download-db-only",
        ],
        env={"MSYS_NO_PATHCONV": "1"},
    )

    (ctx.trivy_cache_dir / ".trivy-db.timestamp").write_text(
        str(int(time.time())) + "\n", encoding="utf-8"
    )
    print()
    print(f"=== Готово: vulnerability DB в {ctx.trivy_cache_dir} ===")
    print(docker_cmd.dir_size_human(ctx.trivy_cache_dir))
