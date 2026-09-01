"""Auto-discovery of Docker/Python/frontend dependencies in a project."""

from __future__ import annotations

import re
from pathlib import Path

from offline_docker.config import DockerfilesConfig, ImagesConfig, ProjectConfig
from offline_docker.defaults import (
    DEFAULT_CRITICAL_WHEELS,
    DEFAULT_DEB_PACKAGES,
    DEFAULT_DOCKER_IMAGES,
)
from offline_docker.utils import parse_apt_packages_from_dockerfiles


def _find_compose_files(root: Path) -> list[str]:
    files = sorted(root.glob("docker-compose*.yml"))
    return [f.name for f in files]


def _find_frontend_dir(root: Path) -> str | None:
    for name in ("frontend", "web", "ui", "fe_mt_react", "client"):
        d = root / name
        if d.is_dir() and (d / "package-lock.json").is_file():
            return name
        if d.is_dir() and (d / "package.json").is_file():
            return name
    return None


def _guess_app_name(root: Path, compose_files: list[str]) -> str:
    for compose in compose_files:
        path = root / compose
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^name:\s*(\S+)", text, re.MULTILINE)
        if m:
            return m.group(1).strip('"').strip("'")
    return root.name.replace("-", "").replace("_", "")[:20] or "app"


def _guess_image_names(root: Path, app_name: str, compose_online: str) -> ImagesConfig:
    images = ImagesConfig()
    online_compose = root / compose_online
    if online_compose.is_file():
        text = online_compose.read_text(encoding="utf-8", errors="replace")
        for svc in ("backend", "frontend"):
            pattern = rf"(?:\w+_)?{svc.upper()}_IMAGE:-([^}}]+)\}}"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tag = match.group(1).strip()
                setattr(images, svc, tag)

        base_match = re.search(r"BASE_IMAGE:\s*\$\{{[^:}]+:-([^}]+)\}", text)
        if base_match:
            images.base = base_match.group(1).strip()

    if images.backend == "app-backend:latest":
        images.backend = f"{root.name}-backend:latest"
    if images.frontend == "app-frontend:latest":
        images.frontend = f"{root.name}-frontend:latest"

    return images


def _detect_python_lock_files(root: Path) -> list[str]:
    candidates = ["pyproject.toml", "uv.lock", "requirements-base.txt", "requirements.txt"]
    return [f for f in candidates if (root / f).is_file()]


def _detect_torch_file(root: Path) -> str:
    for name in ("requirements-base.txt", "requirements.txt"):
        if (root / name).is_file():
            text = (root / name).read_text(encoding="utf-8", errors="replace")
            if "torch==" in text:
                return name
    return "requirements-base.txt"


def _detect_dockerfiles(root: Path) -> DockerfilesConfig:
    df = DockerfilesConfig()
    fe_dir = _find_frontend_dir(root) or "frontend"
    if (root / fe_dir / "Dockerfile.offline").is_file():
        df.frontend_offline = f"{fe_dir}/Dockerfile.offline"
    if (root / fe_dir / "Dockerfile").is_file():
        df.frontend = f"{fe_dir}/Dockerfile"
    for attr in ("base", "base_offline", "backend", "backend_offline"):
        rel = getattr(df, attr)
        if not (root / rel).is_file():
            # keep default; discover will note missing in report
            pass
    return df


def discover_project(root: Path) -> ProjectConfig:
    root = root.resolve()
    compose_files = _find_compose_files(root)
    frontend_dir = _find_frontend_dir(root) or "frontend"
    app_name = _guess_app_name(root, compose_files)
    dockerfiles = _detect_dockerfiles(root)

    deb_from_docker = parse_apt_packages_from_dockerfiles(
        root / dockerfiles.base,
        root / dockerfiles.backend,
    )
    deb_packages = deb_from_docker if deb_from_docker else list(DEFAULT_DEB_PACKAGES)

    compose_offline = "docker-compose.offline.yml"
    compose_online = "docker-compose.yml"
    if compose_offline not in compose_files and compose_files:
        offline_candidates = [f for f in compose_files if "offline" in f]
        if offline_candidates:
            compose_offline = offline_candidates[0]
    if compose_online not in compose_files and compose_files:
        online_candidates = [f for f in compose_files if "offline" not in f and "lab" not in f]
        compose_online = online_candidates[0] if online_candidates else compose_files[0]

    log_dir = root / "storage" / "logs"
    if not log_dir.parent.is_dir():
        log_dir = root / "logs"

    return ProjectConfig(
        root=root,
        offline_cache=root / "offline-cache",
        log_dir=log_dir,
        compose_files=compose_files,
        compose_offline=compose_offline,
        compose_online=compose_online,
        frontend_dir=frontend_dir,
        python_lock_files=_detect_python_lock_files(root),
        torch_version_file=_detect_torch_file(root),
        deb_packages=deb_packages,
        docker_images=list(DEFAULT_DOCKER_IMAGES),
        dockerfiles=dockerfiles,
        images=_guess_image_names(root, app_name, compose_online),
        critical_wheels=list(DEFAULT_CRITICAL_WHEELS),
        app_name=app_name,
        use_uv_export=(root / "uv.lock").is_file() and (root / "pyproject.toml").is_file(),
    )


def format_discovery_report(cfg: ProjectConfig) -> str:
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
        lines.append(f"  - {f}")
    tv = cfg.torch_version()
    lines.extend(
        [
            f"  torch:   {tv or '(не найден)'}",
            f"  uv export: {cfg.use_uv_export}",
            "",
            f"Frontend: {cfg.frontend_dir}/",
            f"  lock: {cfg.frontend_lock}",
            "",
            "Dockerfiles:",
            f"  base:          {cfg.dockerfiles.base}",
            f"  base_offline:  {cfg.dockerfiles.base_offline}",
            f"  backend:       {cfg.dockerfiles.backend_offline}",
            f"  frontend:      {cfg.dockerfiles.frontend_offline}",
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
    return "\n".join(lines)
