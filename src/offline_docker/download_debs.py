"""Download .deb packages into offline-cache/debs."""

from __future__ import annotations

from pathlib import Path

from offline_docker import docker_cmd
from offline_docker.context import ProjectContext
from offline_docker.utils import docker_mount_path


def _build_debs_guest(ctx: ProjectContext) -> str:
    pkgs_bash = " ".join(f'"{p}"' for p in ctx.config.deb_packages)
    extra_repo_script = ""
    for repo in ctx.config.deb_extra_repos:
        gpg_name = Path(repo.gpg_dest).name
        list_name = Path(repo.list_dest).name
        extra_repo_script += f"""
echo ">>> Extra repo: {repo.name}"
curl -fsSL {repo.gpg_url} | gpg --dearmor -o /apt-meta/{gpg_name}
curl -fsSL {repo.list_url} > /apt-meta/{list_name}
cp /apt-meta/{gpg_name} /usr/share/keyrings/{gpg_name}
cp /apt-meta/{list_name} /etc/apt/sources.list.d/{list_name}
apt-get update
"""
    # Optional apt mirrors from package resolver (ProGet deb / Nexus apt)
    apt_mirror_script = ""
    for i, mirror in enumerate(ctx.config.package_resolver().apt_mirrors()):
        # Best-effort: prepend as extra signed-by-less list (corp mirrors vary)
        apt_mirror_script += f"""
echo ">>> Apt mirror from sources[{i}]: {mirror}"
echo "deb [trusted=yes] {mirror} ./" > /etc/apt/sources.list.d/od-mirror-{i}.list
"""
    return f"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# Cache debs is bound to the guest distro: Ubuntu/Debian .deb несовместимы, и
# dpkg -i чужих пакетов ломает базовый образ. Тег образа может переехать
# (python:3.12-slim bookworm -> trixie) — сбрасываем кэш при смене базы.
. /etc/os-release
BASE_OS="$ID-$VERSION_ID"
if [ -f /debs/.base-os ] && [ "$(cat /debs/.base-os)" != "$BASE_OS" ]; then
  echo ">>> База изменилась: $(cat /debs/.base-os) -> $BASE_OS - очищаю старые .deb"
  find /debs -maxdepth 1 -name '*.deb' -delete
fi
printf '%s\\n' "$BASE_OS" > /debs/.base-os

apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg
{apt_mirror_script}
{extra_repo_script}
echo "ok-$(date +%s)" > /apt-meta/.ready

PKGS=({pkgs_bash})

echo ""
echo ">>> Сбор транзитивных зависимостей"
ALL=""
for pkg in "${{PKGS[@]}}"; do
  deps="$(apt-cache depends --recurse --no-recommends \\
    --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances \\
    "$pkg" 2>/dev/null | grep -E "^[[:alnum:]][[:alnum:]._+-]*$" || true)"
  ALL="$ALL $deps"
done
UNIQUE="$(echo "$ALL" | tr " " "\\n" | sort -u | grep -v "^$")"

cd /debs
total="$(echo "$UNIQUE" | wc -l)"
n=0
skipped=0
for pkg in $UNIQUE; do
  n=$((n + 1))
  if compgen -G "${{pkg}}_*.deb" > /dev/null \\
     || compgen -G "${{pkg}}-*.deb" > /dev/null; then
    skipped=$((skipped + 1))
    continue
  fi
  if (( n % 25 == 1 )); then
    echo "    [$n/$total] $pkg ..."
  fi
  apt-get download "$pkg" 2>/dev/null || echo "    WARN: не скачан $pkg" >&2
done

count="$(find /debs -maxdepth 1 -name "*.deb" | wc -l)"
echo ""
echo "=== Готово: ${{count}} .deb в /debs (пропущено уже скачанных: ${{skipped}}) ==="
du -sh /debs
rm -rf /var/lib/apt/lists/*
"""


def download_debs(ctx: ProjectContext) -> None:
    ctx.ensure_offline_dirs()
    from offline_docker.sync_cache import maybe_materialize

    maybe_materialize(ctx)

    debs_docker = docker_mount_path(ctx.debs_dir)
    apt_meta_docker = docker_mount_path(ctx.apt_meta_dir)
    resolver = ctx.config.package_resolver()

    print("=== download-debs ===")
    print(f"Корень:           {ctx.root}")
    print(f"Offline cache:    {ctx.offline_cache}")
    print(f"Ubuntu image:     {ctx.config.deb_ubuntu_image}")
    print(f"Пакетов (seed):   {len(ctx.config.deb_packages)}")
    mirrors = resolver.apt_mirrors()
    if mirrors:
        print(f"Apt mirrors:      {', '.join(mirrors)}")
    print()

    docker_cmd.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{debs_docker}:/debs",
            "-v",
            f"{apt_meta_docker}:/apt-meta",
            ctx.config.deb_ubuntu_image,
            "bash",
            "-ec",
            _build_debs_guest(ctx),
        ],
        env={"DOCKER_BUILDKIT": "0"},
    )

    if resolver.settings.resolve.fill_local:
        from offline_docker.sync_cache import publish_to_remotes

        publish_to_remotes(ctx)

    if not (ctx.apt_meta_dir / ".ready").is_file():
        raise SystemExit(
            "ERROR: apt-meta не попал на хост - проверьте Docker mount path (D:/..., не /d/...)"
        )

    deb_count = len(list(ctx.debs_dir.glob("*.deb")))
    print()
    print(f"Всего .deb: {deb_count}")
