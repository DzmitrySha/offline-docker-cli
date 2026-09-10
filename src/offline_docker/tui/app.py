"""Textual application entry."""

from __future__ import annotations

from pathlib import Path

from textual.app import App

from offline_docker.context import ProjectContext
from offline_docker.tui.screens import HomeScreen


class OfflineDockerApp(App[None]):
    """Interactive TUI for offline-docker actions."""

    TITLE = "offline-docker"
    CSS = """
    Screen {
        background: $surface;
    }
    .title {
        text-style: bold;
        margin: 1 1 0 1;
    }
    #discover-modal {
        width: 90%;
        height: 90%;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }
    #discover-log {
        height: 1fr;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        project: Path,
        *,
        config_file: Path | None = None,
    ) -> None:
        super().__init__()
        self.project = project.resolve()
        self.config_file = config_file
        self.ctx = ProjectContext.load(self.project, config_file=config_file)

    def set_project(self, project: Path, *, config_file: Path | None = None) -> None:
        self.project = project.resolve()
        if config_file is not None:
            self.config_file = config_file
        self.ctx = ProjectContext.load(self.project, config_file=self.config_file)

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())
