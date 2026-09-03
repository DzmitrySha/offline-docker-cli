"""Recursive project inventory for discover/init."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from offline_docker.config import DockerfilesConfig, ImagesConfig, ProjectConfig
from offline_docker.defaults import (
    DEFAULT_CRITICAL_WHEELS,
    DEFAULT_DEB_PACKAGES,
    DEFAULT_DOCKER_IMAGES,
)
from offline_docker.utils import parse_apt_packages_from_dockerfiles

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "offline-cache",
        ".tox",
        "dist",
        "build",
        ".mypy_cache",
        ".ruff_cache",
        "coverage",
        ".idea",
        ".cursor",
        ".pytest_cache",
        ".eggs",
        ".nox",
        "htmlcov",
        ".next",
        ".nuxt",
        "vendor",
    }
)

_FRONTEND_DIR_PRIORITY = ("frontend", "web", "ui", "client", "fe_mt_react")
_FRONTEND_LOCK_NAMES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml")
_FROM_RE = re.compile(
    r"^\s*FROM\s+(?:--platform=\S+\s+)?(?P<img>[^\s]+)(?:\s+AS\s+\S+)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_VAR_FROM_RE = re.compile(r"^\$\{|^[A-Z_][A-Z0-9_]*$")


@dataclass
class ScanInventory:
    compose_files: list[str] = field(default_factory=list)
    dockerfiles: list[str] = field(default_factory=list)
    python_files: list[str] = field(default_factory=list)
    package_json_dirs: list[str] = field(default_factory=list)
    frontend_lock_paths: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    used_default_debs: bool = False


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _should_skip_dir(name: str) -> bool:
    return name in SKIP_DIR_NAMES or name.startswith(".")


def recursive_scan(root: Path) -> ScanInventory:
    """Walk project tree and collect compose/Dockerfile/python/frontend paths."""
    root = root.resolve()
    inv = ScanInventory()
    compose: list[str] = []
    dockerfiles: list[str] = []
    python_files: list[str] = []
    package_json_dirs: list[str] = []
    frontend_locks: list[str] = []

    for dirpath, dirnames, filenames in os_walk_filtered(root):
        base = Path(dirpath)
        for name in filenames:
            path = base / name
            rel = _rel(root, path)
            lower = name.lower()

            if name.startswith("docker-compose") and lower.endswith((".yml", ".yaml")):
                compose.append(rel)
            elif name == "Dockerfile" or name.startswith("Dockerfile."):
                dockerfiles.append(rel)
            elif name in ("pyproject.toml", "uv.lock") or (
                name.startswith("requirements") and name.endswith(".txt")
            ):
                python_files.append(rel)
            elif name == "package.json":
                parent = _rel(root, base) if base != root else "."
                package_json_dirs.append(parent)
            elif name in _FRONTEND_LOCK_NAMES:
                frontend_locks.append(rel)

    inv.compose_files = sorted(set(compose))
    inv.dockerfiles = sorted(set(dockerfiles))
    inv.python_files = sorted(set(python_files))
    inv.package_json_dirs = sorted(set(package_json_dirs))
    inv.frontend_lock_paths = sorted(set(frontend_locks))
    return inv


def os_walk_filtered(root: Path):
    """os.walk-like generator that prunes SKIP_DIR_NAMES in-place."""
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not _should_skip_dir(d))
        yield dirpath, dirnames, filenames


def _path_depth(rel: str) -> int:
    if rel in (".", ""):
        return 0
    return len(Path(rel).parts)


def _pick_frontend(inv: ScanInventory) -> tuple[str, str]:
    """Return (frontend_dir, lock_file_name)."""
    lock_by_dir: dict[str, str] = {}
    for rel in inv.frontend_lock_paths:
        p = Path(rel)
        parent = "." if p.parent == Path(".") else p.parent.as_posix()
        # Prefer package-lock over yarn/pnpm if multiple in same dir
        existing = lock_by_dir.get(parent)
        if existing is None or p.name == "package-lock.json":
            lock_by_dir[parent] = p.name

    candidates = list(lock_by_dir.keys()) or list(inv.package_json_dirs)
    if not candidates:
        return "frontend", "package-lock.json"

    def score(d: str) -> tuple[int, int, str]:
        name = Path(d).name if d != "." else d
        try:
            prio = _FRONTEND_DIR_PRIORITY.index(name)
        except ValueError:
            prio = len(_FRONTEND_DIR_PRIORITY)
        return (prio, _path_depth(d), d)

    chosen = min(candidates, key=score)
    lock_name = lock_by_dir.get(chosen, "package-lock.json")
    return chosen, lock_name


def _is_frontend_dockerfile(rel: str, frontend_dir: str) -> bool:
    if frontend_dir != ".":
        return rel == f"{frontend_dir}/Dockerfile" or rel.startswith(
            f"{frontend_dir}/Dockerfile."
        )
    parts_lower = {p.lower() for p in Path(rel).parts[:-1]}
    return bool(parts_lower & set(_FRONTEND_DIR_PRIORITY))


def _classify_dockerfiles(inv: ScanInventory, frontend_dir: str) -> DockerfilesConfig:
    df = DockerfilesConfig()

    for rel in inv.dockerfiles:
        name = Path(rel).name
        parent = Path(rel).parent.as_posix()
        offline = "offline" in name.lower()

        if _is_frontend_dockerfile(rel, frontend_dir):
            if offline:
                df.frontend_offline = rel
            else:
                df.frontend = rel
            continue

        if name.startswith("Dockerfile.base"):
            if offline:
                df.base_offline = rel
            else:
                df.base = rel
            continue

        if name.startswith("Dockerfile") and offline:
            if parent == "." or any(
                x in parent.lower() for x in ("backend", "api", "server")
            ):
                df.backend_offline = rel
            continue

        if name == "Dockerfile":
            if parent == "." or any(
                x in parent.lower() for x in ("backend", "api", "server")
            ):
                df.backend = rel
            elif "base" in parent.lower():
                df.base = rel

    # Prefer canonical root names when present
    preferred = {
        "base": "Dockerfile.base",
        "base_offline": "Dockerfile.base.offline",
        "backend": "Dockerfile",
        "backend_offline": "Dockerfile.offline",
    }
    for attr, default_name in preferred.items():
        if default_name in inv.dockerfiles:
            setattr(df, attr, default_name)

    if frontend_dir != ".":
        fe_docker = f"{frontend_dir}/Dockerfile"
        fe_offline = f"{frontend_dir}/Dockerfile.offline"
        if fe_docker in inv.dockerfiles:
            df.frontend = fe_docker
        if fe_offline in inv.dockerfiles:
            df.frontend_offline = fe_offline

    return df

def _pick_compose(inv: ScanInventory) -> tuple[list[str], str, str]:
    files = list(inv.compose_files)
    # Prefer root-level compose in listing order (already sorted; root first by depth)
    files_sorted = sorted(files, key=lambda f: (_path_depth(f), f))

    compose_offline = "docker-compose.offline.yml"
    compose_online = "docker-compose.yml"

    offline_candidates = [f for f in files_sorted if "offline" in Path(f).name.lower()]
    online_candidates = [
        f
        for f in files_sorted
        if "offline" not in Path(f).name.lower() and "lab" not in Path(f).name.lower()
    ]

    if offline_candidates:
        compose_offline = offline_candidates[0]
    if online_candidates:
        compose_online = online_candidates[0]
    elif files_sorted:
        compose_online = files_sorted[0]

    return files_sorted, compose_online, compose_offline


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


def _guess_image_names(root: Path, compose_online: str) -> ImagesConfig:
    images = ImagesConfig()
    online_compose = root / compose_online
    if online_compose.is_file():
        text = online_compose.read_text(encoding="utf-8", errors="replace")
        for svc in ("backend", "frontend"):
            pattern = rf"(?:\w+_)?{svc.upper()}_IMAGE:-([^}}]+)\}}"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                setattr(images, svc, match.group(1).strip())

        base_match = re.search(r"BASE_IMAGE:\s*\$\{{[^:}]+:-([^}]+)\}", text)
        if base_match:
            images.base = base_match.group(1).strip()

    if images.backend == "app-backend:latest":
        images.backend = f"{root.name}-backend:latest"
    if images.frontend == "app-frontend:latest":
        images.frontend = f"{root.name}-frontend:latest"
    return images


def _pick_python_lock_files(inv: ScanInventory, dockerfiles: DockerfilesConfig) -> list[str]:
    if not inv.python_files:
        return []

    def score(rel: str) -> tuple[int, int, int, str]:
        depth = _path_depth(rel)
        # Prefer next to backend dockerfile
        backend_parent = Path(dockerfiles.backend).parent.as_posix()
        near_backend = 0
        if backend_parent != "." and rel.startswith(f"{backend_parent}/"):
            near_backend = -1
        elif depth == 0 or Path(rel).parent == Path("."):
            near_backend = -2  # root wins
        name_prio = {
            "pyproject.toml": 0,
            "uv.lock": 1,
            "requirements-base.txt": 2,
            "requirements.txt": 3,
        }.get(Path(rel).name, 9)
        return (near_backend, depth, name_prio, rel)

    ordered = sorted(inv.python_files, key=score)
    # Keep reasonable set: all root files + files in chosen project dir
    root_files = [f for f in ordered if Path(f).parent == Path(".")]
    if root_files:
        return root_files

    # Group by directory; take the shallowest directory's files
    by_dir: dict[str, list[str]] = {}
    for f in ordered:
        parent = "." if Path(f).parent == Path(".") else Path(f).parent.as_posix()
        by_dir.setdefault(parent, []).append(f)
    best_dir = min(by_dir.keys(), key=lambda d: (_path_depth(d), d))
    return by_dir[best_dir]


def _detect_torch_file(root: Path, python_lock_files: list[str]) -> str:
    for rel in python_lock_files:
        if Path(rel).name.startswith("requirements") and (root / rel).is_file():
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
            if "torch==" in text:
                return rel
    for rel in python_lock_files:
        if Path(rel).name.startswith("requirements"):
            return rel
    return "requirements-base.txt"


def parse_from_images(*dockerfiles: Path) -> list[str]:
    """Extract simple FROM image:tag references (skip variables / scratch)."""
    images: list[str] = []
    seen: set[str] = set()
    for dockerfile in dockerfiles:
        if not dockerfile.is_file():
            continue
        text = dockerfile.read_text(encoding="utf-8", errors="replace")
        for m in _FROM_RE.finditer(text):
            img = m.group("img").strip()
            if not img or img.lower() == "scratch":
                continue
            if img.startswith("$") or _VAR_FROM_RE.match(img):
                continue
            if img not in seen:
                seen.add(img)
                images.append(img)
    return images


def _collect_ambiguities(
    inv: ScanInventory, frontend_dir: str, python_lock_files: list[str]
) -> list[str]:
    notes: list[str] = []
    lock_dirs = {
        ("." if Path(p).parent == Path(".") else Path(p).parent.as_posix())
        for p in inv.frontend_lock_paths
    }
    pkg_dirs = set(inv.package_json_dirs)
    fe_candidates = lock_dirs or pkg_dirs
    if len(fe_candidates) > 1:
        others = sorted(fe_candidates - {frontend_dir})
        notes.append(
            f"несколько frontend-кандидатов; выбран {frontend_dir}/ "
            f"(ещё: {', '.join(others)})"
        )

    py_dirs = {
        ("." if Path(p).parent == Path(".") else Path(p).parent.as_posix())
        for p in inv.python_files
    }
    chosen_py_dirs = {
        ("." if Path(p).parent == Path(".") else Path(p).parent.as_posix())
        for p in python_lock_files
    }
    if len(py_dirs) > 1:
        others = sorted(py_dirs - chosen_py_dirs)
        if others:
            notes.append(
                f"несколько python-деревьев; в конфиг: {', '.join(sorted(chosen_py_dirs)) or '(пусто)'} "
                f"(ещё: {', '.join(others)})"
            )
    return notes


def inventory_to_draft_config(root: Path, inventory: ScanInventory) -> ProjectConfig:
    """Map scan inventory to ProjectConfig using broader heuristics."""
    root = root.resolve()
    frontend_dir, frontend_lock = _pick_frontend(inventory)
    dockerfiles = _classify_dockerfiles(inventory, frontend_dir)
    compose_files, compose_online, compose_offline = _pick_compose(inventory)
    python_lock_files = _pick_python_lock_files(inventory, dockerfiles)
    inventory.ambiguities = _collect_ambiguities(
        inventory, frontend_dir, python_lock_files
    )

    app_name = _guess_app_name(root, compose_files)

    deb_from_docker = parse_apt_packages_from_dockerfiles(
        root / dockerfiles.base,
        root / dockerfiles.backend,
    )
    inventory.used_default_debs = not bool(deb_from_docker)
    deb_packages = deb_from_docker if deb_from_docker else list(DEFAULT_DEB_PACKAGES)

    from_imgs = parse_from_images(
        *(root / rel for rel in inventory.dockerfiles)
    )
    docker_images: list[str] = []
    seen_img: set[str] = set()
    for img in list(DEFAULT_DOCKER_IMAGES) + from_imgs:
        if img not in seen_img:
            seen_img.add(img)
            docker_images.append(img)

    log_dir = root / "storage" / "logs"
    if not log_dir.parent.is_dir():
        log_dir = root / "logs"

    cfg = ProjectConfig(
        root=root,
        offline_cache=root / "offline-cache",
        log_dir=log_dir,
        compose_files=compose_files,
        compose_offline=compose_offline,
        compose_online=compose_online,
        compose_build=[compose_online, compose_offline],
        compose_up_offline=[compose_online, compose_offline],
        frontend_dir=frontend_dir,
        frontend_lock=frontend_lock,
        python_lock_files=python_lock_files
        or ["pyproject.toml", "uv.lock", "requirements-base.txt"],
        torch_version_file=_detect_torch_file(root, python_lock_files),
        deb_packages=deb_packages,
        docker_images=docker_images,
        dockerfiles=dockerfiles,
        images=_guess_image_names(root, compose_online),
        critical_wheels=list(DEFAULT_CRITICAL_WHEELS),
        app_name=app_name,
    )
    return cfg


def compute_init_gaps(cfg: ProjectConfig, inventory: ScanInventory) -> list[str]:
    """Human-readable list of missing offline artifacts / ambiguities to fix."""
    gaps: list[str] = []
    root = cfg.root

    def missing(rel: str, label: str) -> None:
        if not (root / rel).is_file():
            gaps.append(f"нет файла {label}: {rel}")

    missing(cfg.dockerfiles.base_offline, "Dockerfile.base.offline")
    missing(cfg.dockerfiles.backend_offline, "Dockerfile.offline (backend)")
    missing(cfg.dockerfiles.frontend_offline, "frontend Dockerfile.offline")

    offline_compose = [
        f for f in inventory.compose_files if "offline" in Path(f).name.lower()
    ]
    if not offline_compose:
        gaps.append(
            f"нет compose с offline в имени (ожидается например {cfg.compose_offline})"
        )

    if not (root / cfg.dockerfiles.base).is_file():
        gaps.append(f"нет base Dockerfile: {cfg.dockerfiles.base}")
    if not (root / cfg.dockerfiles.backend).is_file():
        gaps.append(f"нет backend Dockerfile: {cfg.dockerfiles.backend}")
    if not (root / cfg.dockerfiles.frontend).is_file():
        gaps.append(f"нет frontend Dockerfile: {cfg.dockerfiles.frontend}")

    fe_lock = root / cfg.frontend_dir / cfg.frontend_lock
    if not fe_lock.is_file():
        gaps.append(
            f"не найден frontend lock: {cfg.frontend_dir}/{cfg.frontend_lock}"
        )

    existing_py = [f for f in cfg.python_lock_files if (root / f).is_file()]
    if not existing_py and not inventory.python_files:
        gaps.append("не найдены python lock/requirements (pyproject.toml, uv.lock, requirements*.txt)")

    if inventory.used_default_debs:
        gaps.append(
            "APT-пакеты не извлечены из Dockerfile — в черновике DEFAULT_DEB_PACKAGES; "
            "проверьте debs.packages"
        )

    for note in inventory.ambiguities:
        gaps.append(f"ambiguity: {note}")

    return gaps


def resolve_init_output_path(root: Path) -> Path:
    """Canonical config if absent, else .offline-docker.generated.json."""
    from offline_docker.config import find_project_config_file

    if find_project_config_file(root) is not None:
        return root / ".offline-docker.generated.json"
    return root / ".offline-docker.json"
