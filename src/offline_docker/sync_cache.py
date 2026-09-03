"""Materialize / publish offline-cache trees from remote raw/universal feeds."""

from __future__ import annotations

from pathlib import Path

from offline_docker.context import ProjectContext
from offline_docker.resolve import PackageResolver
from offline_docker.sources.nexus import NexusSource
from offline_docker.sources.nexus_client import download_file, join_url, upload_file
from offline_docker.sources.proget import ProGetSource
from offline_docker.sources.proget_client import download_asset, upload_asset

# Marker files / dirs commonly present after download-*
_SYNC_REL_PATHS = (
    "wheels/.mount-check",
    "wheels/.deps.sha256",
    "npm/.package-lock.sha256",
    "apt-meta/.ready",
)


def materialize_from_remotes(ctx: ProjectContext) -> None:
    """Best-effort pull of known marker/meta files from Nexus raw / ProGet universal."""
    resolver = ctx.config.package_resolver()
    if resolver.is_local_only():
        return

    offline = ctx.offline_cache
    offline.mkdir(parents=True, exist_ok=True)

    for src in resolver.nexus_sources():
        base = src.raw_base_url()
        if not base:
            continue
        print(f">>> materialize from Nexus raw [{src.name}]: {base}")
        for rel in _SYNC_REL_PATHS:
            url = join_url(base, rel)
            dest = offline / rel
            try:
                download_file(url, dest, auth_env=src.auth_env)
                print(f"    OK {rel}")
            except Exception as exc:  # noqa: BLE001 — best-effort sync
                print(f"    skip {rel}: {exc}")

    for src in resolver.proget_sources():
        feed = src.universal_feed()
        if not feed:
            continue
        print(f">>> materialize from ProGet universal [{src.name}/{feed}]")
        for rel in _SYNC_REL_PATHS:
            dest = offline / rel
            try:
                download_asset(src.url, feed, rel, dest, auth_env=src.auth_env)
                print(f"    OK {rel}")
            except FileNotFoundError:
                print(f"    skip {rel}: not found")
            except Exception as exc:  # noqa: BLE001
                print(f"    skip {rel}: {exc}")


def publish_to_remotes(ctx: ProjectContext) -> None:
    """Upload local offline-cache files to remotes with publish=true."""
    resolver = ctx.config.package_resolver()
    offline = ctx.offline_cache
    if not offline.is_dir():
        return

    for src in resolver.nexus_sources():
        if not getattr(src, "publish", False):
            continue
        base = src.raw_base_url()
        if not base:
            print(f"WARN: nexus [{src.name}] publish=true but raw repo not set")
            continue
        print(f">>> publish to Nexus raw [{src.name}]")
        _upload_tree_nexus(offline, base, src.auth_env)

    for src in resolver.proget_sources():
        if not getattr(src, "publish", False):
            continue
        feed = src.universal_feed()
        if not feed:
            print(f"WARN: proget [{src.name}] publish=true but universal feed not set")
            continue
        print(f">>> publish to ProGet [{src.name}/{feed}]")
        _upload_tree_proget(offline, src.url, feed, src.auth_env)


def _upload_tree_nexus(root: Path, base: str, auth_env: str) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        url = join_url(base, rel)
        try:
            upload_file(url, path, auth_env=auth_env)
            print(f"    uploaded {rel}")
        except Exception as exc:  # noqa: BLE001
            print(f"    FAIL {rel}: {exc}")


def _upload_tree_proget(root: Path, base_url: str, feed: str, auth_env: str) -> None:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        try:
            upload_asset(base_url, feed, rel, path, auth_env=auth_env)
            print(f"    uploaded {rel}")
        except Exception as exc:  # noqa: BLE001
            print(f"    FAIL {rel}: {exc}")


def maybe_materialize(ctx: ProjectContext) -> None:
    resolver: PackageResolver = ctx.config.package_resolver()
    if resolver.has_remote_indexes() or any(
        isinstance(s, NexusSource) and s.raw_base_url() for s in resolver.nexus_sources()
    ) or any(
        isinstance(s, ProGetSource) and s.universal_feed() for s in resolver.proget_sources()
    ):
        try:
            materialize_from_remotes(ctx)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: materialize skipped: {exc}")
