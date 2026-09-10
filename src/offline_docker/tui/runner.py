"""Background action runner with stdout/stderr bridge for TUI."""

from __future__ import annotations

import io
import sys
import threading
import traceback
from collections.abc import Callable
from typing import Any

from offline_docker.actions import run_action
from offline_docker.context import ProjectContext


class _LineBridge(io.TextIOBase):
    """Text stream that forwards complete lines to a callback."""

    encoding = "utf-8"

    def __init__(self, on_line: Callable[[str], None]) -> None:
        super().__init__()
        self._on_line = on_line
        self._buf = ""

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:  # type: ignore[override]
        if not s:
            return 0
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._on_line(line.rstrip("\r"))
        return len(s)

    def flush(self) -> None:
        if self._buf:
            self._on_line(self._buf.rstrip("\r"))
            self._buf = ""


def run_action_captured(
    name: str,
    ctx: ProjectContext,
    *,
    on_line: Callable[[str], None],
    on_done: Callable[[int, str | None], None],
    **opts: Any,
) -> threading.Thread:
    """Start run_action in a daemon thread; stream prints via on_line."""

    def worker() -> None:
        bridge = _LineBridge(on_line)
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = bridge  # type: ignore[assignment]
        sys.stderr = bridge  # type: ignore[assignment]
        code = 0
        err: str | None = None
        try:
            run_action(name, ctx, **opts)
        except SystemExit as exc:
            if exc.code is None:
                code = 0
            elif isinstance(exc.code, int):
                code = exc.code
            else:
                code = 1
                err = str(exc.code)
        except Exception as exc:  # noqa: BLE001 — surface to TUI log
            code = 1
            err = f"{type(exc).__name__}: {exc}"
            on_line(err)
            on_line(traceback.format_exc())
        finally:
            try:
                bridge.flush()
            except Exception:  # noqa: BLE001
                pass
            sys.stdout = old_out
            sys.stderr = old_err
            on_done(code, err)

    thread = threading.Thread(target=worker, name=f"offline-docker-{name}", daemon=True)
    thread.start()
    return thread
