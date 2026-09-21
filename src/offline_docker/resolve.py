"""Build ordered package index chains from configured sources."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from offline_docker.sources.base import Ecosystem, PackageSource
from offline_docker.sources.filesystem import FilesystemSource
from offline_docker.sources.nexus import NexusSource
from offline_docker.sources.proget import ProGetSource
from offline_docker.sources.upstream import UpstreamSource


@dataclass
class ResolvePolicy:
    order: list[str] = field(default_factory=lambda: ["local"])
    fill_local: bool = True
    on_miss: str = "fail"  # fail | warn


@dataclass
class CacheSettings:
    sources: list[PackageSource] = field(default_factory=list)
    resolve: ResolvePolicy = field(default_factory=ResolvePolicy)
    cache_config_origin: str = "default"  # default | user | project

    def by_name(self) -> dict[str, PackageSource]:
        return {s.name: s for s in self.sources}

    def ordered_enabled(self) -> list[PackageSource]:
        by_name = self.by_name()
        result: list[PackageSource] = []
        seen: set[str] = set()
        for name in self.resolve.order:
            src = by_name.get(name)
            if src is None or not src.enabled or name in seen:
                continue
            result.append(src)
            seen.add(name)
        return result


class PackageResolver:
    def __init__(self, settings: CacheSettings) -> None:
        self.settings = settings

    def sources(self) -> list[PackageSource]:
        return self.settings.ordered_enabled()

    def index_urls(self, ecosystem: Ecosystem) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for src in self.sources():
            for url in src.index_urls(ecosystem):
                key = url.rstrip("/")
                if key in seen:
                    continue
                seen.add(key)
                urls.append(url)
        return urls

    def pypi_index_chain(self) -> list[str]:
        return self.index_urls("pypi")

    def npm_registries(self) -> list[str]:
        return self.index_urls("npm")

    def primary_npm_registry(self) -> str | None:
        regs = self.npm_registries()
        return regs[0] if regs else None

    def apt_mirrors(self) -> list[str]:
        return self.index_urls("apt")

    def has_remote_indexes(self) -> bool:
        return bool(self.pypi_index_chain() or self.npm_registries() or self.apt_mirrors())

    def is_local_only(self) -> bool:
        return all(getattr(s, "source_type", "") == "filesystem" for s in self.sources())

    def nexus_sources(self) -> list[NexusSource]:
        return [s for s in self.sources() if isinstance(s, NexusSource)]

    def proget_sources(self) -> list[ProGetSource]:
        return [s for s in self.sources() if isinstance(s, ProGetSource)]

    def summary_lines(self) -> list[str]:
        lines = [
            f"Cache config:     {self.settings.cache_config_origin}",
            f"Resolve order:    {', '.join(self.settings.resolve.order)}",
            f"fill_local:       {self.settings.resolve.fill_local}",
            f"on_miss:          {self.settings.resolve.on_miss}",
            "Sources:",
        ]
        by_name = self.settings.by_name()
        for name in self.settings.resolve.order:
            src = by_name.get(name)
            if src is None:
                lines.append(f"  - {name}: (missing)")
                continue
            status = "on" if src.enabled else "off"
            lines.append(f"  - {name} [{src.source_type}] {status}")
            for eco in ("pypi", "npm", "apt"):
                urls = src.index_urls(eco)  # type: ignore[arg-type]
                for u in urls:
                    lines.append(f"      {eco}: {u}")
        pypi = self.pypi_index_chain()
        if pypi:
            lines.append(f"Effective pypi:   {' -> '.join(pypi)}")
        npm = self.npm_registries()
        if npm:
            lines.append(f"Effective npm:    {' -> '.join(npm)}")
        return lines


def _parse_resolve(raw: Any) -> ResolvePolicy:
    if not isinstance(raw, dict):
        return ResolvePolicy()
    order = raw.get("order")
    order_list = [str(x) for x in order] if isinstance(order, list) and order else ["local"]
    return ResolvePolicy(
        order=order_list,
        fill_local=bool(raw.get("fill_local", True)),
        on_miss=str(raw.get("on_miss", "fail")),
    )


def source_from_dict(item: dict[str, Any]) -> PackageSource | None:
    stype = str(item.get("type", "")).lower()
    name = str(item.get("name", stype or "source"))
    enabled = bool(item.get("enabled", True))
    if stype in ("filesystem", "local"):
        return FilesystemSource(name=name, enabled=enabled)
    if stype == "upstream":
        return UpstreamSource(
            name=name,
            enabled=enabled,
            pypi_index=str(item.get("pypi_index", "https://pypi.org/simple")),
            npm_registry=str(item.get("npm_registry", "https://registry.npmjs.org/")),
            pytorch_index=str(item["pytorch_index"]) if item.get("pytorch_index") else None,
        )
    if stype == "nexus":
        repos = item.get("repos") if isinstance(item.get("repos"), dict) else {}
        return NexusSource(
            name=name,
            url=str(item.get("url", "")),
            repos={str(k): str(v) for k, v in repos.items()},
            auth_env=str(item.get("auth_env", "NEXUS_AUTH")),
            enabled=enabled,
            publish=bool(item.get("publish", False)),
            raw_repo=str(item["raw_repo"]) if item.get("raw_repo") else None,
        )
    if stype == "proget":
        feeds = item.get("feeds") if isinstance(item.get("feeds"), dict) else {}
        return ProGetSource(
            name=name,
            url=str(item.get("url", "")),
            feeds={str(k): str(v) for k, v in feeds.items()},
            auth_env=str(item.get("auth_env", "PROGET_API_KEY")),
            enabled=enabled,
            publish=bool(item.get("publish", False)),
        )
    return None


def sources_from_cache_dict(data: dict[str, Any]) -> CacheSettings:
    sources: list[PackageSource] = []
    raw_sources = data.get("sources")
    if isinstance(raw_sources, list):
        for item in raw_sources:
            if isinstance(item, dict):
                src = source_from_dict(item)
                if src is not None:
                    sources.append(src)
    if not any(getattr(s, "source_type", "") == "filesystem" for s in sources):
        sources.insert(0, FilesystemSource())
    resolve = _parse_resolve(data.get("resolve"))
    # Drop empty remote URLs from order effectively via enabled=False on sources
    return CacheSettings(sources=sources, resolve=resolve)


def default_local_only() -> CacheSettings:
    return CacheSettings(
        sources=[FilesystemSource()],
        resolve=ResolvePolicy(order=["local"]),
        cache_config_origin="default",
    )


def apply_env_order_override(settings: CacheSettings) -> CacheSettings:
    raw = os.environ.get("OFFLINE_RESOLVE_ORDER", "").strip()
    if not raw:
        return settings
    order = [part.strip() for part in raw.split(",") if part.strip()]
    if order:
        settings.resolve.order = order
    return settings


def merge_cache_settings(
    *,
    user_data: dict[str, Any] | None,
    project_data: dict[str, Any] | None,
    pypi_index: str,
    pytorch_index: str,
) -> CacheSettings:
    """Project cache section wins entirely when present; else user; else local-only.

    Legacy python.pypi_index is exposed as optional upstream when remotes exist
    or when explicitly enabled in sources.
    """
    origin = "default"
    data: dict[str, Any] | None = None
    if project_data is not None:
        data = project_data
        origin = "project"
    elif user_data is not None:
        data = user_data
        origin = "user"

    if data is None:
        settings = default_local_only()
    else:
        settings = sources_from_cache_dict(data)
        settings.cache_config_origin = origin

    # Ensure filesystem local always present
    if not any(getattr(s, "source_type", "") == "filesystem" for s in settings.sources):
        settings.sources.insert(0, FilesystemSource())

    # If no remote HTTP indexes and no explicit upstream, keep local-only.
    # Attach implicit upstream only when present in sources or when order asks for it.
    by_name = {s.name: s for s in settings.sources}
    if "upstream" in settings.resolve.order and "upstream" not in by_name:
        settings.sources.append(
            UpstreamSource(
                enabled=True,
                pypi_index=pypi_index,
                pytorch_index=pytorch_index,
            )
        )
    else:
        for s in settings.sources:
            if isinstance(s, UpstreamSource) and s.enabled:
                if not s.pytorch_index:
                    s.pytorch_index = pytorch_index
                if s.pypi_index == "https://pypi.org/simple" and pypi_index:
                    s.pypi_index = pypi_index.rstrip("/")

    return apply_env_order_override(settings)


def build_resolver_from_dicts(
    *,
    user_data: dict[str, Any] | None,
    project_cache: dict[str, Any] | None,
    pypi_index: str,
    pytorch_index: str,
) -> PackageResolver:
    settings = merge_cache_settings(
        user_data=user_data,
        project_data=project_cache,
        pypi_index=pypi_index,
        pytorch_index=pytorch_index,
    )
    return PackageResolver(settings)


def pip_index_chain_for_download(
    resolver: PackageResolver,
    *,
    pypi_index: str,
    pytorch_index: str,
) -> tuple[list[str], bool]:
    """HTTP indexes for download-wheels.

    Returns (chain, used_local_only_fallback).
    When sources.json is local-only, chain is empty — we temporarily use
    project/env PyPI + PyTorch indexes so download-* can fill the cache.
    Prefer `offdock configure --with-upstream` to make that explicit.
    """
    chain = list(resolver.pypi_index_chain())
    used_fallback = False
    if not chain:
        chain = [pypi_index, pytorch_index]
        used_fallback = True
    elif pytorch_index and pytorch_index.rstrip("/") not in {
        u.rstrip("/") for u in chain
    }:
        chain.append(pytorch_index)

    # PYPI_INDEX env forces first index when set explicitly
    if os.environ.get("PYPI_INDEX"):
        forced = pypi_index.rstrip("/")
        chain = [pypi_index] + [
            u for u in chain if u.rstrip("/") != forced
        ]
    return chain, used_fallback


def iter_publish_targets(resolver: PackageResolver) -> Iterable[PackageSource]:
    for src in resolver.sources():
        if getattr(src, "publish", False):
            yield src
