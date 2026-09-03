"""offline-docker init: recursive scan → draft .offline-docker.json."""

from __future__ import annotations

import json
from pathlib import Path

from offline_docker.config import project_config_to_dict
from offline_docker.discover import discover_with_inventory, format_discovery_report
from offline_docker.scan import compute_init_gaps, resolve_init_output_path


def run_init(root: Path, *, dry_run: bool = False) -> Path:
    """Build draft config JSON. Returns output path (even on dry-run)."""
    root = root.resolve()
    cfg, inventory = discover_with_inventory(root)
    cfg.config_source = "(init draft)"
    gaps = compute_init_gaps(cfg, inventory)
    out_path = resolve_init_output_path(root)
    out_rel = out_path.name

    data = project_config_to_dict(cfg)
    data["_init"] = {
        "tool": "offline-docker",
        "command": "init",
        "output": out_rel,
        "gaps": gaps,
    }

    report = format_discovery_report(cfg, inventory=inventory, gaps=gaps)
    print(report)
    print()

    if dry_run:
        print(f"[dry-run] черновик НЕ записан (цель: {out_rel})")
        if gaps:
            print(f"[dry-run] gaps: {len(gaps)}")
        return out_path

    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Черновик записан: {out_path}")
    if out_rel == ".offline-docker.generated.json":
        print(
            "Канонический .offline-docker.json/.yaml не изменён "
            "(уже существует в проекте)."
        )
    if gaps:
        print(f"Доработайте вручную ({len(gaps)} пункт(ов) в _init.gaps и секции Missing).")
    else:
        print("Gaps пусты — проверьте пути и при необходимости переименуйте в канон.")
    return out_path
