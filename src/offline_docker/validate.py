"""Validate offline-cache completeness."""

from __future__ import annotations

from pathlib import Path

from offline_docker.context import ProjectContext
from offline_docker.oc_discovery import archive_tar_path, discover_yarn_cache_specs
from offline_docker.utils import file_sha256


def validate_offline_cache(ctx: ProjectContext) -> None:
    errors = 0
    cfg = ctx.config
    resolver = cfg.package_resolver()
    soft = resolver.settings.resolve.on_miss == "warn" and not resolver.is_local_only()

    def fail(msg: str) -> None:
        nonlocal errors
        if soft:
            print(f"WARN: {msg}", flush=True)
        else:
            print(f"ERROR: {msg}", flush=True)
            errors += 1

    def check_dir(d: Path, name: str) -> None:
        if not d.is_dir():
            fail(f"нет каталога {name} ({d})")
            return
        print(f"OK: {name} -> {d}")

    def check_min_files(d: Path, pattern: str, minimum: int, label: str) -> None:
        count = len(list(d.glob(pattern)))
        if count < minimum:
            fail(f"{label} - найдено {count} (минимум {minimum}) в {d}")
        else:
            print(f"OK: {label} - {count} файлов")

    print("=== validate-offline-cache ===")
    print(f"Project:       {ctx.root}")
    print(f"OFFLINE_CACHE: {ctx.offline_cache}")
    print(f"Resolve:       {' -> '.join(resolver.settings.resolve.order)}")
    print(f"on_miss:       {resolver.settings.resolve.on_miss}")
    if soft:
        print("Mode:          soft (WARN instead of ERROR when remotes configured)")
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
            fail("wheels/.mount-check отсутствует - выполните download-wheels")

        if ctx.wheels_hash_file.is_file():
            try:
                current = ctx.python_deps_hash()
                stored = ctx.wheels_hash_file.read_text(encoding="utf-8").strip()
                if current == stored:
                    lock_names = ", ".join(cfg.python_lock_files)
                    print(f"OK: wheels cache соответствует {lock_names}")
                else:
                    fail("Python lockfile изменился - выполните download-wheels")
            except RuntimeError:
                pass
        else:
            fail("нет wheels/.deps.sha256 - выполните download-wheels")

        check_min_files(ctx.wheels_dir, "*.whl", 1, "Python wheels")
        for wp in cfg.critical_wheels:
            if list(ctx.wheels_dir.glob(wp.pattern)):
                print(f"OK: wheel {wp.label}")
            else:
                fail(f"нет {wp.pattern} - выполните download-wheels")
    else:
        print("SKIP: Python wheels (нет lockfile)")

    check_min_files(ctx.debs_dir, "*.deb", 5, "deb-пакеты")

    for repo in cfg.deb_extra_repos:
        gpg = ctx.apt_meta_dir / Path(repo.gpg_dest).name
        lst = ctx.apt_meta_dir / Path(repo.list_dest).name
        if gpg.is_file() and lst.is_file():
            print(f"OK: apt-meta/{repo.name}")
        else:
            fail(f"нет apt-meta для {repo.name} - выполните download-debs")

    if has_frontend:
        if (ctx.npm_cache_dir / "_cacache").is_dir():
            print("OK: npm/_cacache")
        else:
            fail("нет npm/_cacache - выполните download-npm-cache")

        npm_hash = ctx.npm_cache_dir / ".package-lock.sha256"
        lock = cfg.frontend_lock_path()
        assert lock is not None
        if npm_hash.is_file():
            current = file_sha256(lock)
            stored = npm_hash.read_text(encoding="utf-8").strip()
            if current == stored:
                print(f"OK: npm cache соответствует {cfg.frontend_dir}/{cfg.frontend_lock}")
            else:
                fail("package-lock.json изменился - выполните download-npm-cache")
        else:
            fail("нет npm/.package-lock.sha256 - выполните download-npm-cache")
    else:
        print("SKIP: npm cache (нет frontend lockfile)")

    yarn_specs = discover_yarn_cache_specs(cfg)
    if yarn_specs:
        for spec in yarn_specs:
            cache_dir = ctx.offline_cache / spec.cache_subdir
            archive_tar = archive_tar_path(cfg, spec)
            check_dir(cache_dir, spec.cache_subdir)
            check_dir(archive_tar.parent, spec.archive_subdir)
            if archive_tar.is_file():
                print(f"OK: {spec.archive_subdir} archive -> {archive_tar.name}")
            else:
                fail(f"нет {archive_tar.name} - выполните download-yarn-cache")

            yarn_hash = cache_dir / f".{spec.archive_subdir}.sha256"
            if (cache_dir / ".mount-check").is_file():
                print(f"OK: {spec.cache_subdir}/.mount-check")
            else:
                fail(
                    f"{spec.cache_subdir}/.mount-check отсутствует - выполните download-yarn-cache"
                )
            if yarn_hash.is_file() and archive_tar.is_file():
                current = file_sha256(archive_tar)
                stored = yarn_hash.read_text(encoding="utf-8").strip()
                if current == stored:
                    print(f"OK: {spec.cache_subdir} cache соответствует {archive_tar.name}")
                else:
                    fail("archive изменился - выполните download-yarn-cache")
            else:
                fail(
                    f"нет {spec.cache_subdir}/.{spec.archive_subdir}.sha256 - выполните download-yarn-cache"
                )
            cache_entries = [
                p
                for p in cache_dir.iterdir()
                if p.name not in {".mount-check"} and not p.name.startswith(".")
            ]
            v6_dir = cache_dir / "v6"
            if v6_dir.is_dir():
                cache_entries.append(v6_dir)
            if not cache_entries:
                fail(f"{spec.cache_subdir}/ пуст (нет пакетов) - выполните download-yarn-cache")
            else:
                print(f"OK: {spec.cache_subdir} entries - {len(cache_entries)}")
    else:
        print("SKIP: yarn cache (нет source=yarn в *Dockerfile.offline)")

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
