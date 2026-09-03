"""User-level sources config (~/.config/offline-docker/sources.json)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def user_config_dir() -> Path:
    override = os.environ.get("OFFLINE_DOCKER_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "offline-docker"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser() / "offline-docker"
    return Path.home() / ".config" / "offline-docker"


def user_sources_path() -> Path:
    return user_config_dir() / "sources.json"


def local_only_dict() -> dict[str, Any]:
    return {
        "sources": [
            {"name": "local", "type": "filesystem", "enabled": True},
        ],
        "resolve": {
            "order": ["local"],
            "fill_local": True,
            "on_miss": "fail",
        },
    }


def load_user_sources() -> dict[str, Any] | None:
    path = user_sources_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def save_user_sources(data: dict[str, Any]) -> Path:
    path = user_sources_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def user_config_exists() -> bool:
    return user_sources_path().is_file()
