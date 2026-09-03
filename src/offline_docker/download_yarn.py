"""Download yarn cache and dependent oc:// archives (discovered from Dockerfiles)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from offline_docker import docker_cmd
from offline_docker.context import ProjectContext
from offline_docker.oc_discovery import (
    YarnCacheSpec,
    archive_tar_path,
    discover_yarn_cache_specs,
    resolve_build_arg,
)
from offline_docker.utils import docker_mount_path, file_sha256

YARN_GUEST = r"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates git
rm -rf /var/lib/apt/lists/*
yarn config set cache-folder /yarn-cache
yarn install --network-timeout 100000
echo "mount-check-$(date +%s)" > /yarn-cache/.mount-check
"""


def _archive_tag_file(archive_dir: Path, tag: str) -> Path:
    safe = tag.replace("/", "_")
    return archive_dir / f".archive-{safe}.tag"


def download_oc_archive(ctx: ProjectContext, spec: YarnCacheSpec) -> Path:
    if shutil.which("git") is None:
        raise SystemExit("ERROR: git не найден в PATH — нужен для подготовки oc-архива")

    ctx.ensure_offline_dirs()
    version = resolve_build_arg(ctx.config, spec.version_arg, ctx.config.path(spec.source_dockerfile))
    tar = archive_tar_path(ctx.config, spec)
    tag = f"{spec.git_tag_prefix}{version}"
    tag_file = _archive_tag_file(tar.parent, tag)

    if tar.is_file() and tag_file.is_file() and tag_file.read_text(encoding="utf-8").strip() == tag:
        print(f"=== download-oc-archive [{spec.archive_subdir}]: {tag} актуален ===")
        print(docker_cmd.dir_size_human(tar))
        return tar

    print("=== download-oc-archive ===")
    print(f"Subdir:    {spec.archive_subdir}")
    print(f"Version:   {version} ({spec.version_arg})")
    print(f"Repo:      {spec.git_url}")
    print(f"Output:    {tar}")
    print()

    with tempfile.TemporaryDirectory(prefix="od-oc-archive-") as tmp_name:
        tmp = Path(tmp_name)
        clone_dir = tmp / "upstream"
        print(f">>> git clone --depth 1 --branch {tag}")
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                tag,
                spec.git_url,
                str(clone_dir),
            ],
            check=True,
        )
        tar.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["tar", "-czf", str(tar), "-C", str(tmp), "upstream"],
            check=True,
        )

    tag_file.write_text(tag + "\n", encoding="utf-8")
    print()
    print(f"=== Готово: {tar} ===")
    print(docker_cmd.dir_size_human(tar))
    return tar


def download_yarn_cache(ctx: ProjectContext) -> None:
    specs = discover_yarn_cache_specs(ctx.config)
    if not specs:
        print("=== download-yarn-cache: SKIP (нет source=yarn в *Dockerfile.offline) ===")
        return

    for spec in specs:
        _download_yarn_cache_one(ctx, spec)


def _download_yarn_cache_one(ctx: ProjectContext, spec: YarnCacheSpec) -> None:
    ctx.ensure_offline_dirs()
    cache_dir = ctx.offline_cache / spec.cache_subdir
    cache_dir.mkdir(parents=True, exist_ok=True)

    tar = archive_tar_path(ctx.config, spec)
    if not tar.is_file():
        print(f">>> oc/{spec.archive_subdir} не найден, загружаем архив...")
        tar = download_oc_archive(ctx, spec)

    hash_file = cache_dir / f".{spec.archive_subdir}.sha256"
    current = file_sha256(tar)
    marker = cache_dir / ".mount-check"

    if (
        hash_file.is_file()
        and hash_file.read_text(encoding="utf-8").strip() == current
        and marker.is_file()
    ):
        print(f"=== download-yarn-cache [{spec.cache_subdir}]: cache актуален ===")
        print(docker_cmd.dir_size_human(cache_dir))
        return

    yarn_docker = docker_mount_path(cache_dir)

    print("=== download-yarn-cache ===")
    print(f"Cache subdir:  {spec.cache_subdir}")
    print(f"Archive:       {tar}")
    print(f"Node image:    {spec.node_image}")
    print(f"Frontend dir:  {spec.frontend_dir}")
    print()

    with tempfile.TemporaryDirectory(prefix="od-yarn-") as tmp_name:
        tmp = Path(tmp_name)
        subprocess.run(
            ["tar", "-xzf", str(tar), "-C", str(tmp), "--strip-components=1"],
            check=True,
        )
        frontend = tmp / spec.frontend_dir
        if not frontend.is_dir():
            raise SystemExit(f"ERROR: в архиве нет {spec.frontend_dir}/: {tar}")

        frontend_docker = docker_mount_path(frontend)
        docker_cmd.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{yarn_docker}:/yarn-cache",
                "-v",
                f"{frontend_docker}:/work/frontend",
                "-w",
                "/work/frontend",
                spec.node_image,
                "bash",
                "-ec",
                YARN_GUEST,
            ],
            env={"DOCKER_BUILDKIT": "0", "MSYS_NO_PATHCONV": "1"},
        )

    hash_file.write_text(current + "\n", encoding="utf-8")
    print()
    print(f"=== Готово: yarn cache в {cache_dir} ===")
    print(docker_cmd.dir_size_human(cache_dir))
