"""Remove stale wheels that conflict with exact pins in a requirements file.

When offline-cache/wheels still has protobuf-6.32.0.whl but the lock asks for
protobuf==7.36.2, pip --find-links may report only the local version if the
index is unreachable. Deleting mismatched package wheels forces a fresh fetch.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


_REQ_PIN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\\\s;#]+)",
)


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_exact_pins(requirements_text: str) -> dict[str, str]:
    """Return {normalized_name: version} for name==version lines only."""
    pins: dict[str, str] = {}
    for line in requirements_text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or raw.startswith("-"):
            continue
        # Strip env markers: pkg==1.0 ; python_version >= "3.10"
        raw = raw.split(";", 1)[0].strip()
        m = _REQ_PIN.match(raw)
        if not m:
            continue
        pins[normalize_name(m.group(1))] = m.group(2).strip()
    return pins


def parse_wheel_name_version(filename: str) -> tuple[str, str] | None:
    """Best-effort PEP 427 parse: name and version from a .whl filename."""
    if not filename.endswith(".whl"):
        return None
    stem = filename[:-4]
    parts = stem.split("-")
    ver_idx = None
    for i, part in enumerate(parts):
        if part and part[0].isdigit():
            ver_idx = i
            break
    if ver_idx is None or ver_idx == 0:
        return None
    name = normalize_name("-".join(parts[:ver_idx]))
    version = parts[ver_idx]
    return name, version


def parse_sdist_name_version(filename: str) -> tuple[str, str] | None:
    for ext in (".tar.gz", ".zip"):
        if filename.endswith(ext):
            stem = filename[: -len(ext)]
            break
    else:
        return None
    # name-version.tar.gz — version starts at last '-' segment that looks like ver
    parts = stem.rsplit("-", 1)
    if len(parts) != 2 or not parts[1] or not parts[1][0].isdigit():
        return None
    return normalize_name(parts[0]), parts[1]


def artifact_name_version(filename: str) -> tuple[str, str] | None:
    if filename.endswith(".whl"):
        return parse_wheel_name_version(filename)
    return parse_sdist_name_version(filename)


def prune_stale_wheels(requirements_path: Path, wheels_dir: Path) -> list[str]:
    """Delete wheels/sdists for pinned packages whose version is not the pin.

    Returns list of deleted file names.
    """
    if not requirements_path.is_file() or not wheels_dir.is_dir():
        return []
    pins = parse_exact_pins(requirements_path.read_text(encoding="utf-8", errors="replace"))
    if not pins:
        return []

    by_pkg: dict[str, list[tuple[Path, str]]] = {}
    for path in wheels_dir.iterdir():
        if not path.is_file():
            continue
        parsed = artifact_name_version(path.name)
        if parsed is None:
            continue
        name, version = parsed
        if name not in pins:
            continue
        by_pkg.setdefault(name, []).append((path, version))

    deleted: list[str] = []
    for name, wanted in pins.items():
        artifacts = by_pkg.get(name) or []
        if not artifacts:
            continue
        if any(ver == wanted for _, ver in artifacts):
            # Keep matching version; drop other versions of the same package
            for path, ver in artifacts:
                if ver != wanted:
                    path.unlink(missing_ok=True)
                    deleted.append(path.name)
            continue
        # No matching version — remove all stale copies so pip must fetch
        for path, _ver in artifacts:
            path.unlink(missing_ok=True)
            deleted.append(path.name)
    return sorted(deleted)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print(
            "usage: prune_stale_wheels.py <requirements.txt> <wheels_dir>",
            file=sys.stderr,
        )
        return 2
    req = Path(args[0])
    wheels = Path(args[1])
    deleted = prune_stale_wheels(req, wheels)
    if deleted:
        print(f"prune-stale: removed {len(deleted)} artifact(s):")
        for name in deleted:
            print(f"  - {name}")
    else:
        print("prune-stale: nothing to remove")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
