"""Shared helpers: hashes, docker mount paths."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


def docker_mount_path(path: Path | str) -> str:
    """Host path for Docker -v mounts (Windows: D:/... with forward slashes)."""
    p = Path(path).resolve()
    return str(p).replace("\\", "/")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def combined_files_hash(paths: list[Path]) -> str:
    parts = "|".join(file_sha256(p) for p in paths if p.is_file())
    return hashlib.sha256(parts.encode()).hexdigest()


def read_torch_version(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("torch=="):
            return line.split("==", 1)[1].strip()
    raise RuntimeError(f"torch==VERSION not found in {path}")


_APT_INSTALL_RE = re.compile(
    r"apt-get\s+install\b(?:[^\n\\]|\\\s*\n)+",
    re.MULTILINE,
)


def parse_apt_packages_from_dockerfiles(*dockerfiles: Path) -> list[str]:
    """Extract package names from apt-get install lines in Dockerfiles."""
    packages: list[str] = []
    seen: set[str] = set()
    skip = {
        "apt-get",
        "install",
        "-y",
        "--no-install-recommends",
        "&&",
        "rm",
        "-rf",
        "/var/lib/apt/lists/*",
    }

    for dockerfile in dockerfiles:
        if not dockerfile.is_file():
            continue
        text = dockerfile.read_text(encoding="utf-8", errors="replace")
        for block in _APT_INSTALL_RE.findall(text):
            block = block.replace("\\\n", " ")
            for token in re.split(r"[\s\\]+", block):
                token = token.strip().strip('"').strip("'")
                if not token or token in skip or token.startswith("-"):
                    continue
                if token.startswith("/") or "=" in token:
                    continue
                if token not in seen:
                    seen.add(token)
                    packages.append(token)
    return packages
