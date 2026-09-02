"""Discover offline-cache oc:// bind mounts from project Dockerfiles."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from offline_docker.config import ProjectConfig

_OC_MOUNT_RE = re.compile(
    r"from=oc,source=([^,]+),target=([^,\s]+)",
    re.IGNORECASE,
)
_TAR_ARCHIVE_RE = re.compile(
    r'tar\s+-xzf\s+"/oc-[^/]+/([^"]+)"',
    re.IGNORECASE,
)
_NODE_FROM_RE = re.compile(r"^FROM\s+(node:[^\s]+)\s+AS\s+", re.MULTILINE | re.IGNORECASE)
_WORKDIR_RE = re.compile(r"^WORKDIR\s+(/[^\s#]+)", re.MULTILINE)
_GIT_CLONE_RE = re.compile(
    r'git\s+clone\b[^\n]*--branch\s+"([^"]+)"\s*\\?\s*\n\s*(\S+\.git)',
    re.MULTILINE | re.IGNORECASE,
)
_ARG_DEFAULT_RE = re.compile(r"^ARG\s+(\w+)=([^\s#]+)", re.MULTILINE)
_COMPOSE_ARG_DEFAULT_RE = re.compile(
    r"^\s*(\w+):\s*\$\{\1:-([^}]+)\}",
    re.MULTILINE,
)


@dataclass(frozen=True)
class YarnCacheSpec:
    cache_subdir: str
    node_image: str
    archive_subdir: str
    archive_name_template: str
    version_arg: str
    frontend_dir: str
    git_url: str
    git_tag_prefix: str
    source_dockerfile: str


def offline_dockerfile_paths(cfg: ProjectConfig) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in ("**/*Dockerfile.offline", "**/*.Dockerfile.offline"):
        for path in sorted(cfg.root.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                found.append(path)
    return found


def discover_yarn_cache_specs(cfg: ProjectConfig) -> list[YarnCacheSpec]:
    specs: list[YarnCacheSpec] = []
    seen_keys: set[tuple[str, str]] = set()

    for dockerfile in offline_dockerfile_paths(cfg):
        text = dockerfile.read_text(encoding="utf-8", errors="replace")
        if "source=yarn" not in text:
            continue
        spec = _parse_yarn_spec(cfg, dockerfile, text)
        if spec is None:
            continue
        key = (spec.cache_subdir, spec.archive_subdir)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        specs.append(spec)
    return specs


def yarn_cache_needed(cfg: ProjectConfig) -> bool:
    return bool(discover_yarn_cache_specs(cfg))


def archive_tar_path(cfg: ProjectConfig, spec: YarnCacheSpec) -> Path:
    version = resolve_build_arg(cfg, spec.version_arg, cfg.path(spec.source_dockerfile))
    name = spec.archive_name_template.format(version=version)
    return cfg.offline_cache / spec.archive_subdir / name


def resolve_build_arg(cfg: ProjectConfig, arg_name: str, dockerfile: Path) -> str:
    env_val = os.environ.get(arg_name, "").strip()
    if env_val:
        return env_val

    if dockerfile.is_file():
        for match in _ARG_DEFAULT_RE.finditer(dockerfile.read_text(encoding="utf-8", errors="replace")):
            if match.group(1) == arg_name:
                return match.group(2).strip('"').strip("'")

    for compose_name in (
        cfg.compose_offline,
        cfg.compose_online,
        *cfg.compose_build,
        *cfg.compose_files,
    ):
        compose = cfg.path(compose_name)
        if not compose.is_file():
            continue
        text = compose.read_text(encoding="utf-8", errors="replace")
        pattern = re.compile(
            rf"^\s*{re.escape(arg_name)}:\s*\$\{{{re.escape(arg_name)}:-([^}}]+)\}}",
            re.MULTILINE,
        )
        match = pattern.search(text)
        if match:
            return match.group(1).strip().strip('"').strip("'")

    raise RuntimeError(
        f"не удалось определить значение build-arg {arg_name} "
        f"(Dockerfile/compose/env {arg_name})"
    )


def _parse_yarn_spec(cfg: ProjectConfig, dockerfile: Path, text: str) -> YarnCacheSpec | None:
    yarn_subdir: str | None = None
    archive_subdir: str | None = None
    for source, _target in _OC_MOUNT_RE.findall(text):
        if source == "yarn":
            yarn_subdir = source
        elif source not in {"wheels", "npm", "debs"} and archive_subdir is None:
            archive_subdir = source

    if yarn_subdir is None:
        return None

    tar_match = _TAR_ARCHIVE_RE.search(text)
    if tar_match is None or archive_subdir is None:
        return None

    archive_literal = tar_match.group(1)
    version_arg, template = _split_archive_template(archive_literal)
    if version_arg is None:
        return None

    node_image = _NODE_FROM_RE.search(text)
    if node_image is None:
        node_image_name = cfg.node_image
    else:
        node_image_name = node_image.group(1)

    frontend_dir = _frontend_dir_from_workdir(text)
    git_url, tag_prefix = _find_git_source(cfg, version_arg, dockerfile)

    rel = dockerfile.relative_to(cfg.root).as_posix()
    return YarnCacheSpec(
        cache_subdir=yarn_subdir,
        node_image=node_image_name,
        archive_subdir=archive_subdir,
        archive_name_template=template,
        version_arg=version_arg,
        frontend_dir=frontend_dir,
        git_url=git_url,
        git_tag_prefix=tag_prefix,
        source_dockerfile=rel,
    )


def _split_archive_template(archive_literal: str) -> tuple[str | None, str]:
    match = re.search(r"\$\{(\w+)\}", archive_literal)
    if not match:
        return None, archive_literal
    arg = match.group(1)
    template = archive_literal.replace(f"${{{arg}}}", "{version}")
    return arg, template


def _frontend_dir_from_workdir(text: str) -> str:
    workdirs = _WORKDIR_RE.findall(text)
    for path in reversed(workdirs):
        if path.endswith("/frontend") or path == "/frontend":
            return path.split("/")[-1] if "/" in path else path
    return "frontend"


def _find_git_source(cfg: ProjectConfig, version_arg: str, offline_dockerfile: Path) -> tuple[str, str]:
    candidates: list[Path] = []
    if offline_dockerfile.name.endswith(".offline"):
        online_name = offline_dockerfile.name[: -len(".offline")]
        sibling = offline_dockerfile.parent / online_name
        if sibling.is_file():
            candidates.append(sibling)

    for dockerfile in sorted(cfg.root.glob("**/Dockerfile*")):
        if dockerfile.is_file() and dockerfile not in candidates:
            candidates.append(dockerfile)

    for dockerfile in candidates:
        if dockerfile.name.endswith(".offline"):
            continue
        text = dockerfile.read_text(encoding="utf-8", errors="replace")
        for branch_tpl, repo in _GIT_CLONE_RE.findall(text):
            if f"${{{version_arg}}}" not in branch_tpl and version_arg not in branch_tpl:
                continue
            prefix = branch_tpl.split("${", 1)[0]
            if prefix in {"", "v"}:
                return repo, prefix or "v"
            return repo, prefix
    raise RuntimeError(
        f"не найден git clone для build-arg {version_arg} в Dockerfile проекта"
    )
