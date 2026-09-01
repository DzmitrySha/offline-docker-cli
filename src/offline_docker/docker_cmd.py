"""Thin wrappers around docker / docker compose CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


_SUBPROCESS_ENCODING = "utf-8"


def _write_stdout(text: str) -> None:
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(
            text.encode(sys.stdout.encoding or _SUBPROCESS_ENCODING, errors="replace")
        )
    sys.stdout.flush()


class CommandError(RuntimeError):
    def __init__(self, cmd: list[str], returncode: int):
        self.cmd = cmd
        self.returncode = returncode
        super().__init__(f"Command failed ({returncode}): {' '.join(cmd)}")


def require_docker() -> None:
    if shutil.which("docker") is None:
        raise SystemExit("ERROR: docker not found in PATH")


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = subprocess.run(cmd, cwd=cwd, env=merged)
    if check and result.returncode != 0:
        raise CommandError(cmd, result.returncode)
    return result.returncode


def run_capture(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=merged,
        capture_output=True,
        text=True,
        encoding=_SUBPROCESS_ENCODING,
        errors="replace",
    )


def image_exists(image: str) -> bool:
    r = run_capture(["docker", "image", "inspect", image])
    return r.returncode == 0


def run_tee(
    cmd: list[str],
    log_file: Path,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Run command, stream stdout/stderr to console and log file."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    print(f"$ {' '.join(cmd)}  -> {log_file}", flush=True)
    merged = os.environ.copy()
    if env:
        merged.update(env)
    with log_file.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=merged,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding=_SUBPROCESS_ENCODING,
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            _write_stdout(line)
            log.write(line)
        rc = proc.wait()
    if rc != 0:
        raise CommandError(cmd, rc)


def dir_size_human(path: Path) -> str:
    total = 0
    if path.is_file():
        total = path.stat().st_size
    elif path.is_dir():
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    size = float(total)
    for unit in ("B", "K", "M", "G"):
        if size < 1024.0 or unit == "G":
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}G"
