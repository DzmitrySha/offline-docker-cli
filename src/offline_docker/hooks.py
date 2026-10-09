"""Project hooks for offline-cache (e.g. vendor binaries)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from offline_docker import docker_cmd
from offline_docker.config import CacheHook
from offline_docker.context import ProjectContext


def _resolve_command(hook: CacheHook, root: Path) -> list[str] | None:
    """Pick win/sh/script command for the current platform."""
    is_win = os.name == "nt"
    if is_win and hook.win:
        return list(hook.win)
    if (not is_win) and hook.sh:
        return list(hook.sh)
    if hook.script:
        script = root / hook.script
        if not script.is_file():
            raise SystemExit(
                f"ERROR: hooks.after_cache[{hook.name}]: нет файла {hook.script}"
            )
        if script.suffix.lower() == ".ps1":
            return [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ]
        if script.suffix.lower() in {".sh", ".bash"}:
            return ["bash", str(script)]
        if script.suffix.lower() in {".bat", ".cmd"}:
            return ["cmd", "/c", str(script)]
        if os.access(script, os.X_OK):
            return [str(script)]
        return [sys.executable, str(script)]
    if is_win and hook.sh and not hook.win:
        # fallback: try bash (Git Bash / WSL path) only if sh provided alone
        return list(hook.sh)
    if (not is_win) and hook.win and not hook.sh:
        return list(hook.win)
    return None


def run_after_cache_hooks(ctx: ProjectContext) -> None:
    """Run project hooks.after_cache (download vendor, etc.)."""
    hooks = list(ctx.config.after_cache_hooks)
    if not hooks:
        return

    print("========================================")
    print(" hooks.after_cache")
    print(f" Project: {ctx.root}")
    print("========================================")
    print()

    env = {
        "OFFLINE_CACHE": str(ctx.offline_cache),
        f"{ctx.config.app_name.upper()}_OFFLINE_CACHE": str(ctx.offline_cache),
    }

    for hook in hooks:
        cmd = _resolve_command(hook, ctx.root)
        if not cmd:
            raise SystemExit(
                f"ERROR: hooks.after_cache[{hook.name}]: укажите win/sh или script"
            )
        # Resolve relative script tokens in argv to absolute under project root
        resolved: list[str] = []
        for part in cmd:
            p = Path(part)
            if (not p.is_absolute()) and (ctx.root / part).is_file():
                resolved.append(str(ctx.root / part))
            else:
                resolved.append(part)
        print(f">>> hook {hook.name}: {' '.join(resolved)}")
        docker_cmd.run(resolved, cwd=ctx.root, env=env)
        print()
