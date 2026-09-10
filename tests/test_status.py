"""Tests for structured cache status."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from offline_docker.context import ProjectContext
from offline_docker.status import collect_cache_status


class CollectCacheStatusTest(unittest.TestCase):
    def test_empty_project_reports_errors_or_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text("name: test\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\nname='t'\n", encoding="utf-8")
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "python": {"lock_files": ["pyproject.toml"]},
                        "images": {
                            "base": "base:latest",
                            "backend": "backend:latest",
                            "frontend": "frontend:latest",
                        },
                    }
                ),
                encoding="utf-8",
            )
            ctx = ProjectContext.load(root, config_file=cfg_path)
            report = collect_cache_status(ctx)
            self.assertEqual(report.project, root.resolve())
            self.assertGreater(len(report.items), 0)
            levels = {i.level for i in report.items}
            self.assertTrue(levels & {"error", "warn"})
            # Missing cache dirs / wheels should not crash
            self.assertFalse(report.ok)

    def test_skip_python_without_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text("name: test\n", encoding="utf-8")
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "python": {"lock_files": []},
                        "images": {
                            "base": "base:latest",
                            "backend": "backend:latest",
                            "frontend": "frontend:latest",
                        },
                    }
                ),
                encoding="utf-8",
            )
            ctx = ProjectContext.load(root, config_file=cfg_path)
            report = collect_cache_status(ctx)
            skip_labels = [i.label for i in report.items if i.level == "skip"]
            self.assertIn("Python wheels", skip_labels)


if __name__ == "__main__":
    unittest.main()
