"""Offline Trivy image scanning."""

from __future__ import annotations

import shutil

from offline_docker import docker_cmd
from offline_docker.context import ProjectContext
from offline_docker.download_trivy import download_trivy_db, ensure_trivy_image, trivy_db_stale
from offline_docker.utils import docker_mount_path


def scan_trivy_offline(
    ctx: ProjectContext,
    target: str,
    image: str | None = None,
) -> None:
    if target not in ("backend", "frontend"):
        raise SystemExit(f"ERROR: target должен быть backend или frontend, получено: {target}")

    if image is None:
        image = (
            ctx.config.images.backend
            if target == "backend"
            else ctx.config.images.frontend
        )

    if not docker_cmd.image_exists(image):
        raise SystemExit(f"ERROR: образ {image} не найден локально")

    if trivy_db_stale(ctx):
        print("БД Trivy устарела или отсутствует — offdock cache trivy")
        try:
            download_trivy_db(ctx)
        except SystemExit:
            raise
        except Exception as exc:
            raise SystemExit(
                "ERROR: не удалось обновить БД Trivy. "
                "Выполните offdock cache trivy на машине с интернетом."
            ) from exc

    ensure_trivy_image(ctx)
    log_file = ctx.trivy_scan_log(target)
    cache_docker = docker_mount_path(ctx.trivy_cache_dir)
    trivy = ctx.config.trivy

    fanal = ctx.trivy_cache_dir / "fanal"
    if fanal.exists():
        shutil.rmtree(fanal, ignore_errors=True)

    print("=== scan-trivy-offline ===")
    print(f"Target:   {target}")
    print(f"Image:    {image}")
    print(f"Severity: {trivy.severity}")
    print(f"Scanners: {trivy.scanners}")
    print(f"Лог:      {log_file}")
    print()

    docker_cmd.run_tee(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            "/var/run/docker.sock:/var/run/docker.sock",
            "-v",
            f"{cache_docker}:/root/.cache/trivy",
            trivy.scanner_image,
            "image",
            "--skip-db-update",
            "--scanners",
            trivy.scanners,
            "--severity",
            trivy.severity,
            "--exit-code",
            "1",
            "--ignore-unfixed",
            image,
        ],
        log_file,
        env={"MSYS_NO_PATHCONV": "1"},
    )

    print()
    print(f"=== scan-trivy-offline: OK (лог: {log_file}) ===")
