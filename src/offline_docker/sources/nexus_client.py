"""HTTP helpers for Nexus raw repository sync."""

from __future__ import annotations

import base64
import os
import urllib.error
import urllib.request
from pathlib import Path


def _auth_header(auth_env: str) -> dict[str, str]:
    raw = os.environ.get(auth_env, "").strip()
    if not raw:
        return {}
    if raw.lower().startswith("basic ") or raw.lower().startswith("bearer "):
        return {"Authorization": raw}
    if ":" in raw:
        token = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {token}"}
    return {"Authorization": f"Bearer {raw}"}


def _request(
    method: str,
    url: str,
    *,
    auth_env: str,
    data: bytes | None = None,
    content_type: str | None = None,
) -> bytes:
    headers = dict(_auth_header(auth_env))
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Nexus HTTP {exc.code} {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Nexus unreachable {url}: {exc}") from exc


def download_file(url: str, dest: Path, *, auth_env: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = _request("GET", url, auth_env=auth_env)
    dest.write_bytes(data)


def upload_file(url: str, src: Path, *, auth_env: str) -> None:
    data = src.read_bytes()
    _request(
        "PUT",
        url,
        auth_env=auth_env,
        data=data,
        content_type="application/octet-stream",
    )


def join_url(base: str, *parts: str) -> str:
    url = base.rstrip("/")
    for part in parts:
        url = f"{url}/{part.strip('/')}"
    return url
