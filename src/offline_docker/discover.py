"""Auto-discovery of Docker/Python/frontend dependencies in a project."""

from __future__ import annotations

from pathlib import Path

from offline_docker.config import ProjectConfig
from offline_docker.scan import (
    ScanInventory,
    compute_init_gaps,
    inventory_to_draft_config,
    recursive_scan,
)


def discover_project(root: Path) -> ProjectConfig:
    """Recursive scan + role heuristics (shared with init)."""
    root = root.resolve()
    inventory = recursive_scan(root)
    return inventory_to_draft_config(root, inventory)


def discover_with_inventory(root: Path) -> tuple[ProjectConfig, ScanInventory]:
    root = root.resolve()
    inventory = recursive_scan(root)
    cfg = inventory_to_draft_config(root, inventory)
    return cfg, inventory


def format_discovery_report(
    cfg: ProjectConfig,
    *,
    inventory: ScanInventory | None = None,
    gaps: list[str] | None = None,
) -> str:
    if inventory is None:
        inventory = recursive_scan(cfg.root)
    if gaps is None:
        gaps = compute_init_gaps(cfg, inventory)

    lines = [
        f"=== discover: {cfg.root} ===",
        "",
        f"Конфиг:          {cfg.config_source or '(не задан)'}",
        f"App name:         {cfg.app_name}",
        f"Offline cache:    {cfg.offline_cache}",
        f"Log dir:          {cfg.log_dir}",
        "",
        "Compose:",
    ]
    for f in cfg.compose_files or ["(не найдены)"]:
        lines.append(f"  - {f}")
    lines.extend(
        [
            f"  online:  {cfg.compose_online}",
            f"  offline: {cfg.compose_offline}",
            "",
            "Python lock files:",
        ]
    )
    for f in cfg.python_lock_files:
        exists = "ok" if cfg.path(f).is_file() else "missing"
        lines.append(f"  - {f} ({exists})")
    tv = cfg.torch_version()
    lines.extend(
        [
            f"  torch:   {tv or '(не найден)'}",
            f"  uv export: {cfg.use_uv_export}",
            f"  project dir: {cfg.effective_python_project_dir()}",
            "",
            "Yarn cache (oc source=yarn):",
        ]
    )
    from offline_docker.oc_discovery import discover_yarn_cache_specs

    yarn_specs = discover_yarn_cache_specs(cfg)
    for spec in yarn_specs:
        lines.append(
            f"  - cache={spec.cache_subdir}, archive={spec.archive_subdir}, "
            f"arg={spec.version_arg}, dockerfile={spec.source_dockerfile}"
        )
    if not yarn_specs:
        lines.append("  (не требуется)")
    lines.extend(
        [
            "",
            f"Frontend: {cfg.frontend_dir}/",
            f"  lock: {cfg.frontend_lock}",
            "",
            "Dockerfiles:",
            f"  base:             {cfg.dockerfiles.base}",
            f"  base_offline:     {cfg.dockerfiles.base_offline}",
            f"  backend:          {cfg.dockerfiles.backend}",
            f"  backend_offline:  {cfg.dockerfiles.backend_offline}",
            f"  frontend:         {cfg.dockerfiles.frontend}",
            f"  frontend_offline: {cfg.dockerfiles.frontend_offline}",
            "",
            f"APT packages ({len(cfg.deb_packages)}):",
        ]
    )
    for pkg in cfg.deb_packages[:15]:
        lines.append(f"  - {pkg}")
    if len(cfg.deb_packages) > 15:
        lines.append(f"  ... и ещё {len(cfg.deb_packages) - 15}")
    lines.extend(["", "Docker images:"])
    for img in cfg.docker_images:
        lines.append(f"  - {img}")
    lines.extend(
        [
            "",
            "Image tags:",
            f"  base:     {cfg.images.base}",
            f"  backend:  {cfg.images.backend}",
            f"  frontend: {cfg.images.frontend}",
        ]
    )
    if cfg.deb_extra_repos:
        lines.extend(["", "Extra APT repos:"])
        for repo in cfg.deb_extra_repos:
            lines.append(f"  - {repo.name}")

    if inventory.dockerfiles or inventory.python_files or inventory.package_json_dirs:
        lines.extend(["", "Scan inventory (recursive):"])
        lines.append(f"  compose:    {len(inventory.compose_files)}")
        lines.append(f"  dockerfiles:{len(inventory.dockerfiles)}")
        lines.append(f"  python:     {len(inventory.python_files)}")
        lines.append(f"  frontend locks: {len(inventory.frontend_lock_paths)}")

    lines.extend(["", "Missing / to fix:"])
    if gaps:
        for g in gaps:
            lines.append(f"  - {g}")
    else:
        lines.append("  (нет — offline-артефакты на месте)")

    lines.extend(["", "Package sources:"])
    lines.extend(cfg.package_resolver().summary_lines())

    return "\n".join(lines)
