"""Optional Textual TUI for offline-docker."""

from __future__ import annotations

from pathlib import Path


def run_tui(
    project: Path | None = None,
    *,
    config_file: Path | None = None,
) -> int:
    """Launch Textual TUI. Returns process exit code."""
    from offline_docker.tui.app import OfflineDockerApp

    root = (project or Path.cwd()).resolve()
    app = OfflineDockerApp(project=root, config_file=config_file)
    app.run()
    return 0
