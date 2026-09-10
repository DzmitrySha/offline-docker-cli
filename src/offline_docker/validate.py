"""Validate offline-cache completeness."""

from __future__ import annotations

from offline_docker.context import ProjectContext
from offline_docker.status import collect_cache_status


def _format_item_line(level: str, label: str, detail: str) -> str:
    if level == "ok":
        if not detail:
            return f"OK: {label}"
        if detail.startswith("/") or ":\\" in detail or detail.startswith("\\\\"):
            return f"OK: {label} -> {detail}"
        if detail.endswith("файлов") or detail.isdigit():
            return f"OK: {label} - {detail}"
        if detail.startswith("соответствует"):
            return f"OK: {label} {detail}" if "hash" in label or "cache" in label else f"OK: {label} {detail}"
        # paths / archive names / generic
        if "/" in detail or "\\" in detail or detail.endswith(".tar") or detail.endswith(".tar.gz"):
            return f"OK: {label} -> {detail}"
        return f"OK: {label} - {detail}" if " " in detail else f"OK: {label} -> {detail}"
    if level == "skip":
        return f"SKIP: {label} ({detail})" if detail else f"SKIP: {label}"
    prefix = "WARN" if level == "warn" else "ERROR"
    msg = detail or label
    return f"{prefix}: {msg}"


def validate_offline_cache(ctx: ProjectContext) -> None:
    report = collect_cache_status(ctx)

    print("=== validate-offline-cache ===")
    print(f"Project:       {report.project}")
    print(f"OFFLINE_CACHE: {report.offline_cache}")
    print(f"Resolve:       {' -> '.join(report.resolve_order)}")
    print(f"on_miss:       {report.on_miss}")
    if report.soft:
        print("Mode:          soft (WARN instead of ERROR when remotes configured)")
    print()

    for item in report.items:
        line = _format_item_line(item.level, item.label, item.detail)
        if item.level in ("warn", "error"):
            print(line, flush=True)
        else:
            print(line)

    print()
    if report.error_count:
        print(f"=== FAILED: {report.error_count} ошибок ===", flush=True)
        raise SystemExit(1)
    print("=== validate-offline-cache: OK ===")
