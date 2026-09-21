"""Interactive / non-interactive repository source configuration."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from offline_docker.user_config import (
    local_only_dict,
    online_fill_dict,
    save_user_sources,
    user_sources_path,
)

# Helpful placeholders for operators (shown in prompts; Enter keeps empty).
_HINT_PROGET_URL = "https://proget.vitebsk.energo.net"
_HINT_PROGET_PYPI = "ve_pypi"
_HINT_PROGET_NPM = "npm-ve"
_HINT_PROGET_DEB = "local-deb"
_HINT_NEXUS_URL = "http://repos.vitebsk.energo.by:8081"
_HINT_NEXUS_PYPI = "pypi-group"
_HINT_NEXUS_NPM = "npm-group"


def _prompt(label: str, *, hint: str | None = None) -> str:
    suffix = f" [{hint}]" if hint else ""
    try:
        value = input(f"{label}{suffix}: ").strip()
    except EOFError:
        return ""
    return value


def _build_sources_dict(
    *,
    proget_url: str,
    proget_pypi: str,
    proget_npm: str,
    proget_deb: str,
    nexus_url: str,
    nexus_pypi: str,
    nexus_npm: str,
    nexus_raw: str,
    order: list[str] | None = None,
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = [
        {"name": "local", "type": "filesystem", "enabled": True},
    ]
    resolve_order = ["local"]

    if proget_url:
        feeds: dict[str, str] = {}
        if proget_pypi:
            feeds["pypi"] = proget_pypi
        if proget_npm:
            feeds["npm"] = proget_npm
        if proget_deb:
            feeds["deb"] = proget_deb
        sources.append(
            {
                "name": "proget",
                "type": "proget",
                "url": proget_url.rstrip("/"),
                "feeds": feeds,
                "auth_env": "PROGET_API_KEY",
                "enabled": True,
                "publish": False,
            }
        )
        resolve_order.append("proget")
    else:
        sources.append(
            {
                "name": "proget",
                "type": "proget",
                "url": "",
                "feeds": {},
                "auth_env": "PROGET_API_KEY",
                "enabled": False,
                "publish": False,
            }
        )

    if nexus_url:
        repos: dict[str, str] = {}
        if nexus_pypi:
            repos["pypi"] = nexus_pypi
        if nexus_npm:
            repos["npm"] = nexus_npm
        if nexus_raw:
            repos["raw"] = nexus_raw
        sources.append(
            {
                "name": "nexus",
                "type": "nexus",
                "url": nexus_url.rstrip("/"),
                "repos": repos,
                "auth_env": "NEXUS_AUTH",
                "enabled": True,
                "publish": False,
            }
        )
        resolve_order.append("nexus")
    else:
        sources.append(
            {
                "name": "nexus",
                "type": "nexus",
                "url": "",
                "repos": {},
                "auth_env": "NEXUS_AUTH",
                "enabled": False,
                "publish": False,
            }
        )

    if order:
        resolve_order = order

    return {
        "sources": sources,
        "resolve": {
            "order": resolve_order,
            "fill_local": True,
            "on_miss": "fail",
        },
    }


def run_configure(args: argparse.Namespace) -> None:
    if getattr(args, "local_only", False) and getattr(args, "with_upstream", False):
        print("ERROR: укажите либо --local-only, либо --with-upstream", file=sys.stderr)
        raise SystemExit(2)

    if getattr(args, "local_only", False):
        path = save_user_sources(local_only_dict())
        print(f"Сохранено (local-only): {path}")
        print("Режим для офлайн/корп VM: download-* без явного upstream")
        print("  (CLI всё ещё может временно добавить PyPI как fallback — см. WARN).")
        print("Для заполнения кэша с интернета: offline-docker configure --with-upstream")
        return

    if getattr(args, "with_upstream", False):
        path = save_user_sources(online_fill_dict())
        print(f"Сохранено (local + upstream): {path}")
        print("Resolve order: local, upstream")
        print("PyPI: https://pypi.org/simple  |  npm: https://registry.npmjs.org/")
        return

    interactive = sys.stdin.isatty() and not getattr(args, "non_interactive", False)

    proget_url = (getattr(args, "proget_url", None) or "").strip()
    nexus_url = (getattr(args, "nexus_url", None) or "").strip()
    proget_pypi = (getattr(args, "proget_pypi", None) or "").strip()
    proget_npm = (getattr(args, "proget_npm", None) or "").strip()
    proget_deb = (getattr(args, "proget_deb", None) or "").strip()
    nexus_pypi = (getattr(args, "nexus_pypi", None) or "").strip()
    nexus_npm = (getattr(args, "nexus_npm", None) or "").strip()
    nexus_raw = (getattr(args, "nexus_raw", None) or "").strip()
    order_raw = (getattr(args, "order", None) or "").strip()

    flags_given = any(
        getattr(args, name) is not None
        for name in (
            "proget_url",
            "nexus_url",
            "proget_pypi",
            "proget_npm",
            "proget_deb",
            "nexus_pypi",
            "nexus_npm",
            "nexus_raw",
            "order",
        )
    )

    if interactive and not flags_given:
        print("Настройка источников пакетов (Enter = пропустить / пусто).")
        print(f"User config будет записан в: {user_sources_path()}")
        print()
        print("— ProGet —")
        proget_url = _prompt("ProGet base URL", hint=_HINT_PROGET_URL)
        if proget_url:
            proget_pypi = _prompt("ProGet PyPI feed", hint=_HINT_PROGET_PYPI) or _HINT_PROGET_PYPI
            proget_npm = _prompt("ProGet npm feed", hint=_HINT_PROGET_NPM) or _HINT_PROGET_NPM
            proget_deb = _prompt("ProGet deb feed", hint=_HINT_PROGET_DEB) or _HINT_PROGET_DEB
        print()
        print("— Nexus —")
        nexus_url = _prompt("Nexus base URL", hint=_HINT_NEXUS_URL)
        if nexus_url:
            nexus_pypi = _prompt("Nexus PyPI repo", hint=_HINT_NEXUS_PYPI) or _HINT_NEXUS_PYPI
            nexus_npm = _prompt("Nexus npm repo", hint=_HINT_NEXUS_NPM) or _HINT_NEXUS_NPM
            nexus_raw = _prompt("Nexus raw repo (optional)", hint="offline-cache-raw")
        print()
        order_raw = _prompt(
            "Resolve order (comma-separated)",
            hint="local,proget,nexus",
        )

    # Non-interactive defaults for feed names when URL given without feed flags
    if proget_url:
        proget_pypi = proget_pypi or _HINT_PROGET_PYPI
        proget_npm = proget_npm or _HINT_PROGET_NPM
        proget_deb = proget_deb or _HINT_PROGET_DEB
    if nexus_url:
        nexus_pypi = nexus_pypi or _HINT_NEXUS_PYPI
        nexus_npm = nexus_npm or _HINT_NEXUS_NPM

    order: list[str] | None = None
    if order_raw:
        order = [p.strip() for p in order_raw.split(",") if p.strip()]

    if not proget_url and not nexus_url:
        # Без корп. реестров на машине с сетью удобнее local+upstream, чем «тихий» local-only.
        data = online_fill_dict()
        path = save_user_sources(data)
        print(f"URL не заданы — сохранён local + upstream (PyPI/npmjs): {path}")
        print("Только offline-cache: offline-docker configure --local-only")
        return

    data = _build_sources_dict(
        proget_url=proget_url,
        proget_pypi=proget_pypi,
        proget_npm=proget_npm,
        proget_deb=proget_deb,
        nexus_url=nexus_url,
        nexus_pypi=nexus_pypi,
        nexus_npm=nexus_npm,
        nexus_raw=nexus_raw,
        order=order,
    )
    path = save_user_sources(data)
    print(f"Сохранено: {path}")
    print(f"Resolve order: {', '.join(data['resolve']['order'])}")
    print("Auth (опционально): PROGET_API_KEY, NEXUS_AUTH")


def add_configure_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "configure",
        help="Настроить ProGet/Nexus (user-level sources.json)",
        description=(
            "Интерактивная или флаги-настройка источников пакетов. "
            "--with-upstream = local + PyPI/npmjs; --local-only = только offline-cache; "
            "пустые ProGet/Nexus URL в интерактиве = --with-upstream. "
            "Не требует --project."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "примеры:\n"
            "  offline-docker configure\n"
            "  offline-docker configure --with-upstream   # fill cache с PyPI/npmjs\n"
            "  offline-docker configure --local-only      # только offline-cache\n"
            "  offline-docker configure --proget-url https://proget.example.com \\\n"
            "      --nexus-url http://nexus.example.com:8081\n"
        ),
    )
    p.add_argument(
        "--local-only",
        action="store_true",
        help="Только offline-cache (офлайн/корп VM)",
    )
    p.add_argument(
        "--with-upstream",
        action="store_true",
        help="local + PyPI/npmjs upstream (машина с сетью для download-*)",
    )
    p.add_argument("--non-interactive", action="store_true", help="Без prompt (только флаги)")
    p.add_argument("--proget-url", default=None, help="ProGet base URL")
    p.add_argument("--proget-pypi", default=None, help=f"ProGet PyPI feed (hint: {_HINT_PROGET_PYPI})")
    p.add_argument("--proget-npm", default=None, help=f"ProGet npm feed (hint: {_HINT_PROGET_NPM})")
    p.add_argument("--proget-deb", default=None, help=f"ProGet deb feed (hint: {_HINT_PROGET_DEB})")
    p.add_argument("--nexus-url", default=None, help="Nexus base URL")
    p.add_argument("--nexus-pypi", default=None, help=f"Nexus PyPI repo (hint: {_HINT_NEXUS_PYPI})")
    p.add_argument("--nexus-npm", default=None, help=f"Nexus npm repo (hint: {_HINT_NEXUS_NPM})")
    p.add_argument("--nexus-raw", default=None, help="Nexus raw repo for offline-cache mirror")
    p.add_argument(
        "--order",
        default=None,
        help="Resolve order, e.g. local,proget,nexus",
    )
