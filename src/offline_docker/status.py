"""Structured offline-cache status for CLI validate and TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from offline_docker.context import ProjectContext
from offline_docker.oc_discovery import archive_tar_path, discover_yarn_cache_specs
from offline_docker.utils import file_sha256

StatusLevel = Literal["ok", "warn", "error", "skip"]


@dataclass(frozen=True)
class CacheStatusItem:
    level: StatusLevel
    label: str
    detail: str = ""


@dataclass
class CacheStatusReport:
    project: Path
    offline_cache: Path
    resolve_order: list[str]
    on_miss: str
    soft: bool
    items: list[CacheStatusItem] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.items if i.level == "error")

    @property
    def warn_count(self) -> int:
        return sum(1 for i in self.items if i.level == "warn")

    @property
    def ok_count(self) -> int:
        return sum(1 for i in self.items if i.level == "ok")

    @property
    def ok(self) -> bool:
        return self.error_count == 0


def collect_cache_status(ctx: ProjectContext) -> CacheStatusReport:
    cfg = ctx.config
    resolver = cfg.package_resolver()
    soft = resolver.settings.resolve.on_miss == "warn" and not resolver.is_local_only()
    report = CacheStatusReport(
        project=ctx.root,
        offline_cache=ctx.offline_cache,
        resolve_order=list(resolver.settings.resolve.order),
        on_miss=resolver.settings.resolve.on_miss,
        soft=soft,
    )

    def add(level: StatusLevel, label: str, detail: str = "") -> None:
        report.items.append(CacheStatusItem(level=level, label=label, detail=detail))

    def fail(msg: str, *, label: str | None = None) -> None:
        if soft:
            add("warn", label or "cache", msg)
        else:
            add("error", label or "cache", msg)

    def check_dir(d: Path, name: str) -> bool:
        if not d.is_dir():
            fail(f"нет каталога {name} ({d})", label=name)
            return False
        add("ok", name, str(d))
        return True

    def check_min_files(d: Path, pattern: str, minimum: int, label: str) -> None:
        count = len(list(d.glob(pattern)))
        if count < minimum:
            fail(f"найдено {count} (минимум {minimum}) в {d}", label=label)
        else:
            add("ok", label, f"{count} файлов")

    has_python = bool(cfg.python_lock_paths()) or (ctx.root / "requirements.txt").is_file()
    has_frontend = cfg.frontend_lock_path() is not None

    check_dir(ctx.wheels_dir, "wheels")
    check_dir(ctx.debs_dir, "debs")
    check_dir(ctx.npm_cache_dir, "npm")
    check_dir(ctx.docker_cache_dir, "docker")

    if ctx.trivy_cache_dir.is_dir():
        add("ok", "trivy", str(ctx.trivy_cache_dir))
    else:
        add("warn", "trivy", f"нет каталога {ctx.trivy_cache_dir}")

    if has_python:
        if (ctx.wheels_dir / ".mount-check").is_file():
            add("ok", "wheels/.mount-check")
        else:
            fail("wheels/.mount-check отсутствует - выполните download-wheels", label="wheels")

        if ctx.wheels_hash_file.is_file():
            try:
                current = ctx.python_deps_hash()
                stored = ctx.wheels_hash_file.read_text(encoding="utf-8").strip()
                if current == stored:
                    lock_names = ", ".join(cfg.python_lock_files)
                    add("ok", "wheels cache", f"соответствует {lock_names}")
                else:
                    fail("Python lockfile изменился - выполните download-wheels", label="wheels")
            except RuntimeError:
                pass
        else:
            fail("нет wheels/.deps.sha256 - выполните download-wheels", label="wheels")

        check_min_files(ctx.wheels_dir, "*.whl", 1, "Python wheels")
        for wp in cfg.critical_wheels:
            if list(ctx.wheels_dir.glob(wp.pattern)):
                add("ok", f"wheel {wp.label}")
            else:
                fail(f"нет {wp.pattern} - выполните download-wheels", label=f"wheel {wp.label}")
    else:
        add("skip", "Python wheels", "нет lockfile")

    check_min_files(ctx.debs_dir, "*.deb", 5, "deb-пакеты")

    for repo in cfg.deb_extra_repos:
        gpg = ctx.apt_meta_dir / Path(repo.gpg_dest).name
        lst = ctx.apt_meta_dir / Path(repo.list_dest).name
        if gpg.is_file() and lst.is_file():
            add("ok", f"apt-meta/{repo.name}")
        else:
            fail(f"нет apt-meta для {repo.name} - выполните download-debs", label=f"apt-meta/{repo.name}")

    if has_frontend:
        if (ctx.npm_cache_dir / "_cacache").is_dir():
            add("ok", "npm/_cacache")
        else:
            fail("нет npm/_cacache - выполните download-npm-cache", label="npm")

        npm_hash = ctx.npm_cache_dir / ".package-lock.sha256"
        lock = cfg.frontend_lock_path()
        assert lock is not None
        if npm_hash.is_file():
            current = file_sha256(lock)
            stored = npm_hash.read_text(encoding="utf-8").strip()
            if current == stored:
                add("ok", "npm cache", f"соответствует {cfg.frontend_dir}/{cfg.frontend_lock}")
            else:
                fail("package-lock.json изменился - выполните download-npm-cache", label="npm")
        else:
            fail("нет npm/.package-lock.sha256 - выполните download-npm-cache", label="npm")
    else:
        add("skip", "npm cache", "нет frontend lockfile")

    yarn_specs = discover_yarn_cache_specs(cfg)
    if yarn_specs:
        for spec in yarn_specs:
            cache_dir = ctx.offline_cache / spec.cache_subdir
            archive_tar = archive_tar_path(cfg, spec)
            check_dir(cache_dir, spec.cache_subdir)
            check_dir(archive_tar.parent, spec.archive_subdir)
            if archive_tar.is_file():
                add("ok", f"{spec.archive_subdir} archive", archive_tar.name)
            else:
                fail(
                    f"нет {archive_tar.name} - выполните download-yarn-cache",
                    label=spec.archive_subdir,
                )

            yarn_hash = cache_dir / f".{spec.archive_subdir}.sha256"
            if (cache_dir / ".mount-check").is_file():
                add("ok", f"{spec.cache_subdir}/.mount-check")
            else:
                fail(
                    f"{spec.cache_subdir}/.mount-check отсутствует - выполните download-yarn-cache",
                    label=spec.cache_subdir,
                )
            if yarn_hash.is_file() and archive_tar.is_file():
                current = file_sha256(archive_tar)
                stored = yarn_hash.read_text(encoding="utf-8").strip()
                if current == stored:
                    add(
                        "ok",
                        f"{spec.cache_subdir} hash",
                        f"соответствует {archive_tar.name}",
                    )
                else:
                    fail("archive изменился - выполните download-yarn-cache", label=spec.cache_subdir)
            else:
                fail(
                    f"нет {spec.cache_subdir}/.{spec.archive_subdir}.sha256 - выполните download-yarn-cache",
                    label=spec.cache_subdir,
                )
            if cache_dir.is_dir():
                cache_entries = [
                    p
                    for p in cache_dir.iterdir()
                    if p.name not in {".mount-check"} and not p.name.startswith(".")
                ]
                v6_dir = cache_dir / "v6"
                if v6_dir.is_dir():
                    cache_entries.append(v6_dir)
                if not cache_entries:
                    fail(
                        f"{spec.cache_subdir}/ пуст (нет пакетов) - выполните download-yarn-cache",
                        label=spec.cache_subdir,
                    )
                else:
                    add("ok", f"{spec.cache_subdir} entries", str(len(cache_entries)))
    else:
        add("skip", "yarn cache", "нет source=yarn в *Dockerfile.offline")

    tar_count = len(list(ctx.docker_cache_dir.glob("*.tar"))) if ctx.docker_cache_dir.is_dir() else 0
    if tar_count >= 1:
        add("ok", "docker tars", f"{tar_count} файлов")
    else:
        add("warn", "docker tars", "нет docker/*.tar - выполните download-docker-images")

    return report
