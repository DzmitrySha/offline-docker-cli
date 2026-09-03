"""ProGet universal/asset feed helpers (optional mirror of offline-cache tree)."""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote


def _api_key_header(auth_env: str) -> dict[str, str]:
    key = os.environ.get(auth_env, "").strip()
    if not key:
        return {}
    if key.lower().startswith("x-api-key:"):
        return {"X-ApiKey": key.split(":", 1)[1].strip()}
    return {"X-ApiKey": key}


def download_asset(base_url: str, feed: str, path: str, dest: Path, *, auth_env: str) -> None:
    url = f"{base_url.rstrip('/')}/endpoints/{quote(feed)}/content/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers=_api_key_header(auth_env))
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FileNotFoundError(path) from exc
        raise RuntimeError(f"ProGet HTTP {exc.code} {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ProGet unreachable {url}: {exc}") from exc


def upload_asset(base_url: str, feed: str, path: str, src: Path, *, auth_env: str) -> None:
    url = f"{base_url.rstrip('/')}/endpoints/{quote(feed)}/content/{path.lstrip('/')}"
    data = src.read_bytes()
    headers = dict(_api_key_header(auth_env))
    headers["Content-Type"] = "application/octet-stream"
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"ProGet HTTP {exc.code} {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"ProGet unreachable {url}: {exc}") from exc
