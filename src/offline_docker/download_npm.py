"""Download npm cache for frontend."""

from __future__ import annotations

from offline_docker import docker_cmd
from offline_docker.context import ProjectContext
from offline_docker.utils import docker_mount_path, file_sha256

# POSIX /bin/sh (node:*-alpine has no bash; node ENTRYPOINT would otherwise exec "node bash")
NPM_GUEST = r"""
set -euo pipefail
cp /app-src/package.json /app-src/package-lock.json . 2>/dev/null || cp /app-src/package.json .
if [ ! -f package-lock.json ]; then
  echo "ERROR: package-lock.json не найден - нужен lockfile для offline npm ci" >&2
  exit 1
fi
npm config set cache /npm-cache
npm config set registry "${NPM_REGISTRY}"
# HTTP corporate registries (e.g. Nexus without TLS)
case "${NPM_REGISTRY}" in
  http://*) npm config set strict-ssl false ;;
esac
npm ci --no-audit --no-fund
echo "mount-check-$(date +%s)" > /npm-cache/.mount-check
"""


def download_npm_cache(ctx: ProjectContext) -> None:
    fe = ctx.config.frontend_path()
    lock = ctx.config.frontend_lock_path()
    if fe is None or lock is None:
        print("=== download-npm-cache: SKIP (frontend/package-lock.json не найден) ===")
        return

    ctx.ensure_offline_dirs()
    hash_file = ctx.npm_cache_dir / ".package-lock.sha256"
    current = file_sha256(lock)
    cacache = ctx.npm_cache_dir / "_cacache"

    if (
        hash_file.is_file()
        and hash_file.read_text(encoding="utf-8").strip() == current
        and cacache.is_dir()
    ):
        print("=== download-npm-cache: package-lock.json не менялся, cache актуален ===")
        print(docker_cmd.dir_size_human(ctx.npm_cache_dir))
        return

    from offline_docker.sync_cache import maybe_materialize

    maybe_materialize(ctx)

    resolver = ctx.config.package_resolver()
    registry = resolver.primary_npm_registry() or "https://registry.npmjs.org/"

    frontend_docker = docker_mount_path(fe)
    npm_docker = docker_mount_path(ctx.npm_cache_dir)

    print("=== download-npm-cache ===")
    print(f"Frontend:       {fe}")
    print(f"npm cache dir:  {ctx.npm_cache_dir}")
    print(f"Node image:     {ctx.config.node_image}")
    print(f"Resolve:        {' -> '.join(resolver.settings.resolve.order)}")
    print(f"npm registry:   {registry}")

    docker_cmd.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/sh",
            "-e",
            f"NPM_REGISTRY={registry}",
            "-v",
            f"{frontend_docker}:/app-src:ro",
            "-v",
            f"{npm_docker}:/npm-cache",
            "-w",
            "/work",
            ctx.config.node_image,
            "-ec",
            NPM_GUEST,
        ],
        env={"DOCKER_BUILDKIT": "0", "MSYS_NO_PATHCONV": "1"},
    )

    hash_file.write_text(current + "\n", encoding="utf-8")
    print()
    print(f"=== Готово: npm cache в {ctx.npm_cache_dir} ===")
    print(docker_cmd.dir_size_human(ctx.npm_cache_dir))

    if resolver.settings.resolve.fill_local:
        from offline_docker.sync_cache import publish_to_remotes

        publish_to_remotes(ctx)
