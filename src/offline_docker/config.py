"""Project configuration: load YAML/JSON, merge with auto-discovery."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from offline_docker.defaults import (
    DEFAULT_CRITICAL_WHEELS,
    DEFAULT_DEB_PACKAGES,
    DEFAULT_DOCKER_IMAGES,
    WheelPattern,
)
from offline_docker.utils import read_torch_version


@dataclass
class DebExtraRepo:
    name: str
    gpg_url: str
    list_url: str
    gpg_dest: str
    list_dest: str


@dataclass
class DockerfilesConfig:
    base: str = "Dockerfile.base"
    base_offline: str = "Dockerfile.base.offline"
    backend: str = "Dockerfile"
    backend_offline: str = "Dockerfile.offline"
    frontend: str = "frontend/Dockerfile"
    frontend_offline: str = "frontend/Dockerfile.offline"


@dataclass
class ImagesConfig:
    base: str = "neuroai-base:cuda12"
    backend: str = "app-backend:latest"
    frontend: str = "app-frontend:latest"


@dataclass
class TrivyConfig:
    scanner_image: str = "aquasec/trivy:latest"
    cache_subdir: str = "trivy"
    db_max_age_days: int = 7
    severity: str = "HIGH,CRITICAL"
    scanners: str = "vuln"


@dataclass
class ProjectConfig:
    root: Path
    offline_cache: Path
    log_dir: Path
    compose_files: list[str] = field(default_factory=list)
    compose_build: list[str] = field(default_factory=list)
    compose_up_offline: list[str] = field(default_factory=list)
    compose_up_offline_lab: list[str] = field(default_factory=list)
    compose_offline: str = "docker-compose.offline.yml"
    compose_online: str = "docker-compose.yml"
    frontend_dir: str = "frontend"
    frontend_lock: str = "package-lock.json"
    python_lock_files: list[str] = field(
        default_factory=lambda: ["pyproject.toml", "uv.lock", "requirements-base.txt"]
    )
    torch_version_file: str = "requirements-base.txt"
    pytorch_index: str = "https://download.pytorch.org/whl/cu128"
    pypi_index: str = "https://pypi.org/simple"
    deb_ubuntu_image: str = "ubuntu:24.04"
    deb_packages: list[str] = field(default_factory=list)
    deb_extra_repos: list[DebExtraRepo] = field(default_factory=list)
    docker_images: list[str] = field(default_factory=list)
    dockerfiles: DockerfilesConfig = field(default_factory=DockerfilesConfig)
    images: ImagesConfig = field(default_factory=ImagesConfig)
    critical_wheels: list[WheelPattern] = field(default_factory=list)
    trivy: TrivyConfig = field(default_factory=TrivyConfig)
    build_services: list[str] = field(
        default_factory=lambda: ["base", "backend", "frontend"]
    )
    app_name: str = "app"
    node_image: str = "node:22-bookworm-slim"
    use_uv_export: bool = True
    uv_export_prune: list[str] = field(
        default_factory=lambda: ["torch", "torchaudio"]
    )
    extra_wheel_specs: list[str] = field(default_factory=list)
    config_source: str | None = None

    def path(self, rel: str) -> Path:
        return self.root / rel

    def python_lock_paths(self) -> list[Path]:
        return [self.path(f) for f in self.python_lock_files if self.path(f).is_file()]

    def frontend_path(self) -> Path | None:
        d = self.path(self.frontend_dir)
        return d if d.is_dir() else None

    def frontend_lock_path(self) -> Path | None:
        fe = self.frontend_path()
        if fe is None:
            return None
        lock = fe / self.frontend_lock
        return lock if lock.is_file() else None

    def compose_build_file_args(self) -> list[str]:
        """`-f` args: online manifest + offline build override."""
        files = self.compose_build or [self.compose_online, self.compose_offline]
        args: list[str] = []
        for rel in files:
            args.extend(["-f", rel])
        return args

    def compose_up_file_args(self, *, lab: bool = False) -> list[str]:
        """`-f` args для offline runtime (up-offline)."""
        if lab:
            files = self.compose_up_offline_lab or [
                *(
                    self.compose_up_offline
                    or self.compose_build
                    or [self.compose_online, self.compose_offline]
                ),
                "docker-compose.lab.yml",
            ]
        else:
            files = self.compose_up_offline or self.compose_build or [
                self.compose_online,
                self.compose_offline,
            ]
        args: list[str] = []
        for rel in files:
            args.extend(["-f", rel])
        return args

    def torch_version(self) -> str | None:
        tv_file = self.path(self.torch_version_file)
        if not tv_file.is_file():
            return None
        try:
            return read_torch_version(tv_file)
        except RuntimeError:
            return None


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    elif path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            json_alt = path.with_suffix(".json")
            if json_alt.is_file():
                return _load_yaml_or_json(json_alt)
            raise SystemExit(
                f"ERROR: для {path.name} нужен PyYAML или JSON-версия ({json_alt.name})"
            ) from exc
        data = yaml.safe_load(text)
    else:
        raise SystemExit(f"ERROR: неподдерживаемый формат конфига: {path}")
    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: конфиг {path} должен быть объектом JSON/YAML")
    return data


def _parse_deb_extra_repos(raw: list[Any]) -> list[DebExtraRepo]:
    repos: list[DebExtraRepo] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        repos.append(
            DebExtraRepo(
                name=str(item.get("name", "extra")),
                gpg_url=str(item["gpg_url"]),
                list_url=str(item["list_url"]),
                gpg_dest=str(item.get("gpg_dest", f"apt-meta/{item.get('name', 'extra')}.gpg")),
                list_dest=str(
                    item.get("list_dest", f"apt-meta/{item.get('name', 'extra')}.list")
                ),
            )
        )
    return repos


def _parse_critical_wheels(raw: list[Any]) -> list[WheelPattern]:
    wheels: list[WheelPattern] = []
    for item in raw:
        if isinstance(item, dict):
            wheels.append(
                WheelPattern(str(item["pattern"]), str(item.get("label", item["pattern"])))
            )
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            wheels.append(WheelPattern(str(item[0]), str(item[1])))
    return wheels


def _merge_config_dict(base: ProjectConfig, data: dict[str, Any]) -> ProjectConfig:
    if "offline_cache" in data:
        base.offline_cache = base.path(str(data["offline_cache"]))
    if "log_dir" in data:
        base.log_dir = base.path(str(data["log_dir"]))
    if "compose_files" in data:
        base.compose_files = [str(x) for x in data["compose_files"]]
    if "compose_offline" in data:
        base.compose_offline = str(data["compose_offline"])
    if "compose_online" in data:
        base.compose_online = str(data["compose_online"])
    if "compose_build" in data:
        base.compose_build = [str(x) for x in data["compose_build"]]
    if "compose_up_offline" in data:
        base.compose_up_offline = [str(x) for x in data["compose_up_offline"]]
    if "compose_up_offline_lab" in data:
        base.compose_up_offline_lab = [str(x) for x in data["compose_up_offline_lab"]]
    if "app_name" in data:
        base.app_name = str(data["app_name"])
    if "node_image" in data:
        base.node_image = str(data["node_image"])
    if "use_uv_export" in data:
        base.use_uv_export = bool(data["use_uv_export"])

    py = data.get("python", {})
    if isinstance(py, dict):
        if "lock_files" in py:
            base.python_lock_files = [str(x) for x in py["lock_files"]]
        if "torch_version_file" in py:
            base.torch_version_file = str(py["torch_version_file"])
        if "pytorch_index" in py:
            base.pytorch_index = str(py["pytorch_index"])
        if "pypi_index" in py:
            base.pypi_index = str(py["pypi_index"])
        if "uv_export_prune" in py:
            base.uv_export_prune = [str(x) for x in py["uv_export_prune"]]
        if "extra_wheel_specs" in py:
            base.extra_wheel_specs = [str(x) for x in py["extra_wheel_specs"]]

    fe = data.get("frontend", {})
    if isinstance(fe, dict):
        if "dir" in fe:
            base.frontend_dir = str(fe["dir"])
        if "lock_file" in fe:
            base.frontend_lock = str(fe["lock_file"])

    debs = data.get("debs", {})
    if isinstance(debs, dict):
        if "ubuntu_image" in debs:
            base.deb_ubuntu_image = str(debs["ubuntu_image"])
        if "packages" in debs:
            base.deb_packages = [str(x) for x in debs["packages"]]
        if "extra_repos" in debs:
            base.deb_extra_repos = _parse_deb_extra_repos(debs["extra_repos"])

    if "docker_images" in data:
        base.docker_images = [str(x) for x in data["docker_images"]]

    df = data.get("dockerfiles", {})
    if isinstance(df, dict):
        for key in (
            "base",
            "base_offline",
            "backend",
            "backend_offline",
            "frontend",
            "frontend_offline",
        ):
            if key in df:
                setattr(base.dockerfiles, key, str(df[key]))

    imgs = data.get("images", {})
    if isinstance(imgs, dict):
        if "base" in imgs:
            base.images.base = str(imgs["base"])
        elif "base_online" in imgs:
            base.images.base = str(imgs["base_online"])
        elif "base_offline" in imgs:
            base.images.base = str(imgs["base_offline"]).replace(":offline", ":cuda12")

        if "backend" in imgs:
            base.images.backend = str(imgs["backend"])
        elif "backend_offline" in imgs:
            tag = str(imgs["backend_offline"])
            base.images.backend = tag.replace(":offline", ":latest")

        if "frontend" in imgs:
            base.images.frontend = str(imgs["frontend"])
        elif "frontend_offline" in imgs:
            tag = str(imgs["frontend_offline"])
            base.images.frontend = tag.replace(":offline", ":latest")

    val = data.get("validate", {})
    if isinstance(val, dict) and "critical_wheels" in val:
        base.critical_wheels = _parse_critical_wheels(val["critical_wheels"])

    trivy = data.get("trivy", {})
    if isinstance(trivy, dict):
        for key in ("scanner_image", "cache_subdir", "severity", "scanners"):
            if key in trivy:
                setattr(base.trivy, key, str(trivy[key]))
        if "db_max_age_days" in trivy:
            base.trivy.db_max_age_days = int(trivy["db_max_age_days"])

    if "build_services" in data:
        base.build_services = [str(x) for x in data["build_services"]]

    return base


def find_project_config_file(root: Path) -> Path | None:
    for name in (".offline-docker.yaml", ".offline-docker.yml", ".offline-docker.json"):
        path = root / name
        if path.is_file():
            return path
    return None


def resolve_offline_cache(root: Path, app_name: str, configured: Path | None) -> Path:
    for key in ("OFFLINE_CACHE", f"{app_name.upper()}_OFFLINE_CACHE"):
        val = os.environ.get(key)
        if val:
            p = Path(val)
            return p if p.is_absolute() else root / p
    if configured is not None:
        return configured if configured.is_absolute() else root / configured
    return root / "offline-cache"


def load_config(
    root: Path,
    *,
    config_file: Path | None = None,
) -> ProjectConfig:
    from offline_docker.discover import discover_project

    root = root.resolve()
    cfg: ProjectConfig | None = None
    source: str | None = None

    if config_file and config_file.is_file():
        cfg = _merge_config_dict(discover_project(root), _load_yaml_or_json(config_file))
        source = str(config_file.resolve())
    else:
        project_config = find_project_config_file(root)
        if project_config is not None:
            cfg = _merge_config_dict(
                discover_project(root), _load_yaml_or_json(project_config)
            )
            source = str(project_config.resolve())

    if cfg is None:
        cfg = discover_project(root)
        source = "(auto-discovery)"

    cfg.config_source = source
    cfg.root = root
    cfg.offline_cache = resolve_offline_cache(root, cfg.app_name, cfg.offline_cache)
    if not cfg.log_dir.is_absolute():
        cfg.log_dir = root / cfg.log_dir

    if not cfg.deb_packages:
        cfg.deb_packages = list(DEFAULT_DEB_PACKAGES)
    if not cfg.docker_images:
        cfg.docker_images = list(DEFAULT_DOCKER_IMAGES)
    if not cfg.critical_wheels:
        cfg.critical_wheels = list(DEFAULT_CRITICAL_WHEELS)

    return cfg
