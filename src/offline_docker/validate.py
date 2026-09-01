"""Validate offline-cache completeness."""

from __future__ import annotations

from pathlib import Path

from offline_docker.context import ProjectContext
from offline_docker.utils import file_sha256


def validate_offline_cache(ctx: ProjectContext) -> None:
    errors = 0
    cfg = ctx.config

    def check_dir(d: Path, name: str) -> None:
        nonlocal errors
        if not d.is_dir():
            print(f"ERROR: нет каталога {name} ({d})", flush=True)
            errors += 1
            return
        print(f"OK: {name} -> {d}")

    def check_min_files(d: Path, pattern: str, minimum: int, label: str) -> None:
        nonlocal errors
        count = len(list(d.glob(pattern)))
        if count < minimum:
            print(
                f"ERROR: {label} - найдено {count} (минимум {minimum}) в {d}",
                flush=True,
            )
            errors += 1
        else:
            print(f"OK: {label} - {count} файлов")

    print("=== validate-offline-cache ===")
    print(f"Project:       {ctx.root}")
    print(f"OFFLINE_CACHE: {ctx.offline_cache}")
    print()

    has_python = bool(cfg.python_lock_paths()) or (ctx.root / "requirements.txt").is_file()
    has_frontend = cfg.frontend_lock_path() is not None

    check_dir(ctx.wheels_dir, "wheels")
    check_dir(ctx.debs_dir, "debs")
    check_dir(ctx.npm_cache_dir, "npm")
    check_dir(ctx.docker_cache_dir, "docker")

    if has_python:
        if (ctx.wheels_dir / ".mount-check").is_file():
            print("OK: wheels/.mount-check")
        else:
            print(
                "ERROR: wheels/.mount-check отсутствует - выполните download-wheels",
                flush=True,
            )
            errors += 1

        if ctx.wheels_hash_file.is_file():
            try:
                current = ctx.python_deps_hash()
                stored = ctx.wheels_hash_file.read_text(encoding="utf-8").strip()
                if current == stored:
                    lock_names = ", ".join(cfg.python_lock_files)
                    print(f"OK: wheels cache соответствует {lock_names}")
                else:
                    print(
                        "ERROR: Python lockfile изменился - выполните download-wheels",
                        flush=True,
                    )
                    errors += 1
            except RuntimeError:
                pass
        else:
            print(
                "ERROR: нет wheels/.deps.sha256 - выполните download-wheels",
                flush=True,
            )
            errors += 1

        check_min_files(ctx.wheels_dir, "*.whl", 1, "Python wheels")
        for wp in cfg.critical_wheels:
            if list(ctx.wheels_dir.glob(wp.pattern)):
                print(f"OK: wheel {wp.label}")
            else:
                print(
                    f"ERROR: нет {wp.pattern} - выполните download-wheels",
                    flush=True,
                )
                errors += 1
    else:
        print("SKIP: Python wheels (нет lockfile)")

    check_min_files(ctx.debs_dir, "*.deb", 5, "deb-пакеты")

    for repo in cfg.deb_extra_repos:
        gpg = ctx.apt_meta_dir / Path(repo.gpg_dest).name
        lst = ctx.apt_meta_dir / Path(repo.list_dest).name
        if gpg.is_file() and lst.is_file():
            print(f"OK: apt-meta/{repo.name}")
        else:
            print(
                f"ERROR: нет apt-meta для {repo.name} - выполните download-debs",
                flush=True,
            )
            errors += 1

    if has_frontend:
        if (ctx.npm_cache_dir / "_cacache").is_dir():
            print("OK: npm/_cacache")
        else:
            print(
                "ERROR: нет npm/_cacache - выполните download-npm-cache",
                flush=True,
            )
            errors += 1

        npm_hash = ctx.npm_cache_dir / ".package-lock.sha256"
        lock = cfg.frontend_lock_path()
        assert lock is not None
        if npm_hash.is_file():
            current = file_sha256(lock)
            stored = npm_hash.read_text(encoding="utf-8").strip()
            if current == stored:
                print(f"OK: npm cache соответствует {cfg.frontend_dir}/{cfg.frontend_lock}")
            else:
                print(
                    "ERROR: package-lock.json изменился - выполните download-npm-cache",
                    flush=True,
                )
                errors += 1
        else:
            print(
                "ERROR: нет npm/.package-lock.sha256 - выполните download-npm-cache",
                flush=True,
            )
            errors += 1
    else:
        print("SKIP: npm cache (нет frontend lockfile)")

    tar_count = len(list(ctx.docker_cache_dir.glob("*.tar")))
    if tar_count >= 1:
        print(f"OK: docker tar-файлов - {tar_count}")
    else:
        print(
            "WARN: нет docker/*.tar - выполните download-docker-images",
            flush=True,
        )

    print()
    if errors:
        print(f"=== FAILED: {errors} ошибок ===", flush=True)
        raise SystemExit(1)
    print("=== validate-offline-cache: OK ===")
