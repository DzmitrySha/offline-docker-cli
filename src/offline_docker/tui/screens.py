"""Textual screens for offline-docker TUI."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from offline_docker.actions import PROJECT_ACTIONS
from offline_docker.discover import format_discovery_report
from offline_docker.status import CacheStatusReport, collect_cache_status
from offline_docker.tui.runner import run_action_captured

# User-facing command list (order matters).
_COMMANDS: list[tuple[str, str]] = [
    ("discover", "Discover dependencies"),
    ("cache-check", "Validate offline-cache"),
    ("cache", "Download full offline-cache"),
    ("cache-wheels", "Download wheels"),
    ("cache-debs", "Download debs"),
    ("cache-npm", "Download npm cache"),
    ("cache-yarn", "Download yarn cache"),
    ("cache-images", "Download docker images"),
    ("cache-trivy", "Download Trivy DB"),
    ("cache-load", "Load docker images"),
    ("build", "Build offline (base/backend/frontend)"),
    ("build-base", "Build base offline"),
    ("up", "Compose up offline"),
    ("up-online", "Up online (compose_online)"),
    ("down", "Compose down"),
    ("scan:backend", "Trivy scan backend"),
    ("scan:frontend", "Trivy scan frontend"),
]


class DiscoverModal(ModalScreen[None]):
    """Modal with discover report text."""

    BINDINGS = [Binding("escape", "dismiss", "Close", show=True)]

    def __init__(self, report: str) -> None:
        super().__init__()
        self._report = report

    def compose(self) -> ComposeResult:
        with Vertical(id="discover-modal"):
            yield Static("Discover report", classes="title")
            log = RichLog(highlight=False, markup=False, id="discover-log")
            yield log
            yield Button("Close", id="close-discover", variant="primary")

    def on_mount(self) -> None:
        log = self.query_one("#discover-log", RichLog)
        for line in self._report.splitlines():
            log.write(line)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-discover":
            self.dismiss()


class HomeScreen(Screen[None]):
    """Project path, cache status, commands, live log."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=True),
        Binding("d", "discover", "Discover", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    CSS = """
    #project-row {
        height: auto;
        margin: 0 1;
    }
    #project-input {
        width: 1fr;
    }
    #summary {
        margin: 0 1;
        height: 1;
        color: $text-muted;
    }
    #status-table {
        height: 12;
        margin: 0 1;
    }
    #flags {
        height: auto;
        margin: 0 1;
    }
    #commands {
        height: 10;
        margin: 0 1;
        border: solid $primary;
    }
    #run-log {
        height: 1fr;
        margin: 0 1 1 1;
        border: solid $accent;
    }
    #actions-row {
        height: auto;
        margin: 0 1;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._running = False
        self._selected_command: str | None = None

    def compose(self) -> ComposeResult:
        app = self.app
        from offline_docker.tui.app import OfflineDockerApp

        assert isinstance(app, OfflineDockerApp)
        yield Header(show_clock=False)
        with Vertical():
            yield Static("offdock TUI", classes="title")
            with Horizontal(id="project-row"):
                yield Label("Project:")
                yield Input(value=str(app.project), id="project-input")
                yield Button("Load", id="btn-load", variant="primary")
                yield Button("Refresh", id="btn-refresh")
            yield Static("", id="summary")
            yield DataTable(id="status-table", zebra_stripes=True)
            with Horizontal(id="flags"):
                yield Checkbox("no-cache", id="flag-no-cache")
                yield Checkbox("lab (up)", id="flag-lab")
                yield Checkbox("online (up/down)", id="flag-online")
                yield Checkbox("no-build", id="flag-no-build")
                yield Checkbox("no-deps", id="flag-no-deps")
            yield Label("Commands (Enter / Run):")
            yield ListView(id="commands", *self._command_items())
            with Horizontal(id="actions-row"):
                yield Button("Run", id="btn-run", variant="success")
                yield Button("Discover report", id="btn-discover")
            yield RichLog(highlight=False, markup=False, id="run-log", wrap=True)
        yield Footer()

    @staticmethod
    def _command_items() -> list[ListItem]:
        items: list[ListItem] = []
        for key, title in _COMMANDS:
            items.append(ListItem(Label(f"{title}  ({key})"), id=f"cmd-{key.replace(':', '-')}"))
        return items

    def on_mount(self) -> None:
        table = self.query_one("#status-table", DataTable)
        table.add_columns("Level", "Label", "Detail")
        table.cursor_type = "row"
        self.action_refresh()

    def _app(self):
        from offline_docker.tui.app import OfflineDockerApp

        app = self.app
        assert isinstance(app, OfflineDockerApp)
        return app

    def action_refresh(self) -> None:
        self._reload_status()

    def action_discover(self) -> None:
        self._show_discover()

    def action_quit(self) -> None:
        self.app.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-load":
            self._load_project_from_input()
        elif bid == "btn-refresh":
            self._reload_status()
        elif bid == "btn-discover":
            self._show_discover()
        elif bid == "btn-run":
            self._run_selected()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        idx = event.list_view.index
        if idx is None or idx < 0 or idx >= len(_COMMANDS):
            return
        self._selected_command = _COMMANDS[idx][0]

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        if idx is None or idx < 0 or idx >= len(_COMMANDS):
            return
        self._selected_command = _COMMANDS[idx][0]
        self._run_selected()

    def _load_project_from_input(self) -> None:
        raw = self.query_one("#project-input", Input).value.strip()
        if not raw:
            self.notify("Укажите путь к проекту", severity="warning")
            return
        path = Path(raw).expanduser().resolve()
        if not path.is_dir():
            self.notify(f"Каталог не найден: {path}", severity="error")
            return
        try:
            self._app().set_project(path)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"Не удалось загрузить конфиг: {exc}", severity="error")
            return
        self.notify(f"Проект: {path}")
        self._reload_status()

    def _reload_status(self) -> None:
        app = self._app()
        try:
            report = collect_cache_status(app.ctx)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"Status error: {exc}", severity="error")
            return
        self._fill_status(report)

    def _fill_status(self, report: CacheStatusReport) -> None:
        summary = self.query_one("#summary", Static)
        mode = " soft" if report.soft else ""
        summary.update(
            f"cache={report.offline_cache}  "
            f"OK={report.ok_count} WARN={report.warn_count} ERROR={report.error_count}{mode}  "
            f"resolve={' -> '.join(report.resolve_order)}"
        )
        table = self.query_one("#status-table", DataTable)
        table.clear()
        for item in report.items:
            table.add_row(item.level.upper(), item.label, item.detail or "")

    def _show_discover(self) -> None:
        try:
            text = format_discovery_report(self._app().ctx.config)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"Discover error: {exc}", severity="error")
            return
        self.app.push_screen(DiscoverModal(text))

    def _flag(self, widget_id: str) -> bool:
        return self.query_one(f"#{widget_id}", Checkbox).value

    def _run_selected(self) -> None:
        if self._running:
            self.notify("Уже выполняется команда", severity="warning")
            return
        key = self._selected_command
        if not key:
            lv = self.query_one("#commands", ListView)
            if lv.index is not None and 0 <= lv.index < len(_COMMANDS):
                key = _COMMANDS[lv.index][0]
        if not key:
            self.notify("Выберите команду", severity="warning")
            return

        name = key
        opts: dict = {
            "no_cache": self._flag("flag-no-cache"),
            "lab": self._flag("flag-lab"),
            "online": self._flag("flag-online"),
            "no_build": self._flag("flag-no-build"),
            "no_deps": self._flag("flag-no-deps"),
        }
        if key.startswith("scan:"):
            name = "scan"
            opts["target"] = key.split(":", 1)[1]
        if name == "up-online":
            name = "up"
            opts["online"] = True
            opts["lab"] = False
        if opts.get("lab") and opts.get("online"):
            self.notify("--lab и --online взаимоисключающие; снимите один флаг", severity="warning")
            return

        if name not in PROJECT_ACTIONS:
            self.notify(f"Неизвестная команда: {name}", severity="error")
            return

        log = self.query_one("#run-log", RichLog)
        log.clear()
        log.write(f">>> {name} {opts}")
        self._running = True
        self.query_one("#btn-run", Button).disabled = True

        app = self._app()

        def on_line(line: str) -> None:
            app.call_from_thread(log.write, line)

        def on_done(code: int, err: str | None) -> None:
            def finish() -> None:
                self._running = False
                self.query_one("#btn-run", Button).disabled = False
                if err:
                    log.write(f"!!! {err}")
                log.write(f"=== exit {code} ===")
                if code == 0:
                    self.notify(f"{name}: OK")
                    self._reload_status()
                else:
                    self.notify(f"{name}: failed ({code})", severity="error")

            app.call_from_thread(finish)

        run_action_captured(name, app.ctx, on_line=on_line, on_done=on_done, **opts)
