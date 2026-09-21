"""Tests for shared actions dispatch."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from offline_docker.actions import PROJECT_ACTIONS, run_action
from offline_docker.context import ProjectContext


class RunActionTest(unittest.TestCase):
    def test_discover_prints_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text(
                "name: demo\nservices:\n  backend:\n    image: demo-backend:latest\n",
                encoding="utf-8",
            )
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "app_name": "demo",
                        "images": {
                            "base": "base:latest",
                            "backend": "demo-backend:latest",
                            "frontend": "demo-frontend:latest",
                        },
                    }
                ),
                encoding="utf-8",
            )
            ctx = ProjectContext.load(root, config_file=cfg_path)
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_action("discover", ctx)
            out = buf.getvalue()
            self.assertIn("discover", out.lower())
            self.assertIn(str(root.resolve()), out)

    def test_unknown_action_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text("name: t\n", encoding="utf-8")
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text("{}", encoding="utf-8")
            ctx = ProjectContext.load(root, config_file=cfg_path)
            with self.assertRaises(ValueError):
                run_action("not-a-real-command", ctx)

    def test_project_actions_nonempty(self) -> None:
        self.assertIn("discover", PROJECT_ACTIONS)
        self.assertIn("download-offline-cache", PROJECT_ACTIONS)
        self.assertIn("cache", PROJECT_ACTIONS)
        self.assertIn("down", PROJECT_ACTIONS)


if __name__ == "__main__":
    unittest.main()
