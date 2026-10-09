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
from offline_docker.resolve import CacheSettings, PackageResolver, default_local_only
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
class CacheHook:
    """Project hook run after standard offline-cache downloads."""

    name: str
    win: list[str] = field(default_factory=list)
    sh: list[str] = field(default_factory=list)
    script: str | None = None


@dataclass
class VendorPathCheck:
    """Required path under offline-cache (glob allowed), e.g. vendor/VERSIONS."""

    path: str
    label: str


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
    compose_env_file: str | None = None
    compose_env_files: list[str] = field(default_factory=list)
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
    critical_vendor: list[VendorPathCheck] = field(default_factory=list)
    after_cache_hooks: list[CacheHook] = field(default_factory=list)
    trivy: TrivyConfig = field(default_factory=TrivyConfig)
    build_services: list[str] = field(
        default_factory=lambda: ["base", "backend", "frontend"]
    )
    app_name: str = "app"
    node_image: str = "node:22-bookworm-slim"
    use_uv_export: bool = True
    explicit_use_uv_export: bool = field(default=False, repr=False)
    explicit_python_project_dir: bool = field(default=False, repr=False)
    python_project_dir: str | None = None
    uv_export_prune: list[str] = field(
        default_factory=lambda: ["torch", "torchaudio"]
    )
    extra_wheel_specs: list[str] = field(default_factory=list)
    config_source: str | None = None
    # Raw project "cache" section if present (wins over user-config).
    project_cache_data: dict[str, Any] | None = field(default=None, repr=False)
    cache_settings: CacheSettings = field(default_factory=default_local_only)
    cache_config_origin: str = "default"

    def path(self, rel: str) -> Path:
        return self.root / rel

    def package_resolver(self) -> PackageResolver:
        return PackageResolver(self.cache_settings)

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

    def compose_env_file_args(self) -> list[str]:
        """`--env-file` args for compose ${VAR} interpolation.

        Uses ``compose_env_files`` (list) when set; otherwise legacy
        ``compose_env_file``. Later files override earlier ones (Compose
        behaviour), so put secrets last.
        """
        rels = list(self.compose_env_files)
        if not rels and self.compose_env_file:
            rels = [self.compose_env_file]
        args: list[str] = []
        for rel in rels:
            path = self.path(rel)
            if not path.is_file():
                continue
            args.extend(["--env-file", rel])
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

    @staticmethod
    def _normalize_project_dir(rel: str) -> str:
        d = rel.strip().strip("/")
        return "." if not d else d

    def infer_python_project_dir(self) -> str:
        pyproject_dirs: list[str] = []
        uv_lock_dirs: list[str] = []
        for rel in self.python_lock_files:
            p = Path(rel)
            if not self.path(rel).is_file():
                continue
            parent = self._normalize_project_dir(
                "." if p.parent == Path(".") else p.parent.as_posix()
            )
            if p.name == "pyproject.toml":
                pyproject_dirs.append(parent)
            elif p.name == "uv.lock":
                uv_lock_dirs.append(parent)

        if pyproject_dirs and uv_lock_dirs:
            common = set(pyproject_dirs) & set(uv_lock_dirs)
            if common:
                return min(common, key=len)
            return pyproject_dirs[0]
        if pyproject_dirs:
            return pyproject_dirs[0]

        for dockerfile in (self.dockerfiles.backend_offline, self.dockerfiles.backend):
            parent = Path(dockerfile).parent
            if parent != Path(".") and self.path(str(parent / "pyproject.toml")).is_file():
                return self._normalize_project_dir(parent.as_posix())

        if self.path("pyproject.toml").is_file():
            return "."
        return "."

    def effective_python_project_dir(self) -> str:
        if self.python_project_dir is not None:
            return self._normalize_project_dir(self.python_project_dir)
        return self.infer_python_project_dir()

    def infer_use_uv_export(self) -> bool:
        proj = self.effective_python_project_dir()
        base = self.root if proj == "." else self.root / proj
        return (base / "uv.lock").is_file() and (base / "pyproject.toml").is_file()


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


def _parse_critical_vendor(raw: list[Any]) -> list[VendorPathCheck]:
    items: list[VendorPathCheck] = []
    for item in raw:
        if isinstance(item, dict):
            path = str(item.get("path") or item.get("pattern") or "")
            if not path:
                continue
            items.append(VendorPathCheck(path, str(item.get("label", path))))
        elif isinstance(item, str):
            items.append(VendorPathCheck(item, item))
        elif isinstance(item, (list, tuple)) and len(item) >= 1:
            path = str(item[0])
            label = str(item[1]) if len(item) >= 2 else path
            items.append(VendorPathCheck(path, label))
    return items


def _parse_after_cache_hooks(raw: list[Any]) -> list[CacheHook]:
    hooks: list[CacheHook] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("script") or "hook")
        win = [str(x) for x in item.get("win", [])] if isinstance(item.get("win"), list) else []
        sh = [str(x) for x in item.get("sh", [])] if isinstance(item.get("sh"), list) else []
        script = str(item["script"]) if item.get("script") else None
        # Convenience: "run" as platform-neutral argv
        run = item.get("run")
        if isinstance(run, list) and run:
            argv = [str(x) for x in run]
            if not win:
                win = list(argv)
            if not sh:
                sh = list(argv)
        hooks.append(CacheHook(name=name, win=win, sh=sh, script=script))
    return hooks


def dockerfile_uses_vendor_mount(cfg: ProjectConfig) -> bool:
    """True if any offline Dockerfile bind-mounts source=vendor from oc."""
    candidates = (
        cfg.dockerfiles.backend_offline,
        cfg.dockerfiles.base_offline,
        cfg.dockerfiles.frontend_offline,
    )
    for rel in candidates:
        path = cfg.path(rel)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "source=vendor" in text:
            return True
    return False


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
    if "compose_env_file" in data:
        base.compose_env_file = str(data["compose_env_file"])
    if "compose_env_files" in data:
        base.compose_env_files = [str(x) for x in data["compose_env_files"]]
    if "app_name" in data:
        base.app_name = str(data["app_name"])
    if "node_image" in data:
        base.node_image = str(data["node_image"])
    if "use_uv_export" in data:
        base.use_uv_export = bool(data["use_uv_export"])
        base.explicit_use_uv_export = True

    py = data.get("python", {})
    if isinstance(py, dict):
        if "project_dir" in py:
            base.python_project_dir = str(py["project_dir"])
            base.explicit_python_project_dir = True
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
    if isinstance(val, dict):
        if "critical_wheels" in val:
            base.critical_wheels = _parse_critical_wheels(val["critical_wheels"])
        if "critical_vendor" in val:
            base.critical_vendor = _parse_critical_vendor(val["critical_vendor"])

    hooks = data.get("hooks", {})
    if isinstance(hooks, dict) and "after_cache" in hooks:
        raw_hooks = hooks["after_cache"]
        if isinstance(raw_hooks, list):
            base.after_cache_hooks = _parse_after_cache_hooks(raw_hooks)

    trivy = data.get("trivy", {})
    if isinstance(trivy, dict):
        for key in ("scanner_image", "cache_subdir", "severity", "scanners"):
            if key in trivy:
                setattr(base.trivy, key, str(trivy[key]))
        if "db_max_age_days" in trivy:
            base.trivy.db_max_age_days = int(trivy["db_max_age_days"])

    if "build_services" in data:
        base.build_services = [str(x) for x in data["build_services"]]

    if "cache" in data and isinstance(data["cache"], dict):
        base.project_cache_data = dict(data["cache"])

    return base


def project_config_to_dict(cfg: ProjectConfig) -> dict[str, Any]:
    """Serialize ProjectConfig to .offline-docker.json shape (example schema)."""
    offline_cache = cfg.offline_cache
    if offline_cache.is_absolute():
        try:
            offline_cache_rel = offline_cache.relative_to(cfg.root).as_posix()
        except ValueError:
            offline_cache_rel = str(offline_cache)
    else:
        offline_cache_rel = Path(offline_cache).as_posix()

    log_dir = cfg.log_dir
    if log_dir.is_absolute():
        try:
            log_dir_rel = log_dir.relative_to(cfg.root).as_posix()
        except ValueError:
            log_dir_rel = str(log_dir)
    else:
        log_dir_rel = Path(log_dir).as_posix()

    data: dict[str, Any] = {
        "offline_cache": offline_cache_rel,
        "log_dir": log_dir_rel,
        "app_name": cfg.app_name,
        "compose_online": cfg.compose_online,
        "compose_offline": cfg.compose_offline,
        "compose_build": cfg.compose_build
        or [cfg.compose_online, cfg.compose_offline],
        "compose_up_offline": cfg.compose_up_offline
        or [cfg.compose_online, cfg.compose_offline],
        "python": {
            "lock_files": list(cfg.python_lock_files),
            "torch_version_file": cfg.torch_version_file,
            "pytorch_index": cfg.pytorch_index,
        },
        "frontend": {
            "dir": cfg.frontend_dir,
            "lock_file": cfg.frontend_lock,
        },
        "dockerfiles": {
            "base": cfg.dockerfiles.base,
            "base_offline": cfg.dockerfiles.base_offline,
            "backend": cfg.dockerfiles.backend,
            "backend_offline": cfg.dockerfiles.backend_offline,
            "frontend": cfg.dockerfiles.frontend,
            "frontend_offline": cfg.dockerfiles.frontend_offline,
        },
        "images": {
            "base": cfg.images.base,
            "backend": cfg.images.backend,
            "frontend": cfg.images.frontend,
        },
        "debs": {
            "ubuntu_image": cfg.deb_ubuntu_image,
            "packages": list(cfg.deb_packages),
            "extra_repos": [
                {
                    "name": r.name,
                    "gpg_url": r.gpg_url,
                    "list_url": r.list_url,
                    "gpg_dest": r.gpg_dest,
                    "list_dest": r.list_dest,
                }
                for r in cfg.deb_extra_repos
            ],
        },
        "docker_images": list(cfg.docker_images),
        "validate": {
            "critical_wheels": [
                {"pattern": w.pattern, "label": w.label} for w in cfg.critical_wheels
            ],
            "critical_vendor": [
                {"path": v.path, "label": v.label} for v in cfg.critical_vendor
            ],
        },
        "trivy": {
            "scanner_image": cfg.trivy.scanner_image,
            "db_max_age_days": cfg.trivy.db_max_age_days,
            "severity": cfg.trivy.severity,
            "scanners": cfg.trivy.scanners,
        },
        "build_services": list(cfg.build_services),
    }
    if cfg.after_cache_hooks:
        data["hooks"] = {
            "after_cache": [
                {
                    "name": h.name,
                    **({"script": h.script} if h.script else {}),
                    **({"win": list(h.win)} if h.win else {}),
                    **({"sh": list(h.sh)} if h.sh else {}),
                }
                for h in cfg.after_cache_hooks
            ]
        }
    if cfg.compose_up_offline_lab:
        data["compose_up_offline_lab"] = list(cfg.compose_up_offline_lab)
    if cfg.python_project_dir and cfg.python_project_dir != ".":
        data["python"]["project_dir"] = cfg.python_project_dir
    if cfg.compose_env_files:
        data["compose_env_files"] = list(cfg.compose_env_files)
    elif cfg.compose_env_file:
        data["compose_env_file"] = cfg.compose_env_file
    return data


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

    if not cfg.explicit_python_project_dir:
        cfg.python_project_dir = cfg.infer_python_project_dir()
    elif cfg.python_project_dir is None:
        cfg.python_project_dir = cfg.infer_python_project_dir()
    if not cfg.explicit_use_uv_export:
        cfg.use_uv_export = cfg.infer_use_uv_export()

    from offline_docker.resolve import merge_cache_settings
    from offline_docker.user_config import load_user_sources

    user_data = load_user_sources()
    cfg.cache_settings = merge_cache_settings(
        user_data=user_data,
        project_data=cfg.project_cache_data,
        pypi_index=cfg.pypi_index,
        pytorch_index=cfg.pytorch_index,
    )
    cfg.cache_config_origin = cfg.cache_settings.cache_config_origin

    return cfg
