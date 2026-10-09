"""Tests for after_cache hooks and vendor validation config."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from offline_docker.config import (
    CacheHook,
    dockerfile_uses_vendor_mount,
    load_config,
)
from offline_docker.context import ProjectContext
from offline_docker.hooks import _resolve_command, run_after_cache_hooks
from offline_docker.status import collect_cache_status


class HooksConfigTest(unittest.TestCase):
    def test_parse_hooks_and_critical_vendor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text("name: t\n", encoding="utf-8")
            (root / "Dockerfile.offline").write_text(
                "FROM ubuntu:24.04\n"
                "RUN --mount=type=bind,from=oc,source=vendor,target=/vendor,ro true\n",
                encoding="utf-8",
            )
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "python": {"lock_files": []},
                        "dockerfiles": {"backend_offline": "Dockerfile.offline"},
                        "hooks": {
                            "after_cache": [
                                {
                                    "name": "vendor",
                                    "script": "scripts/cache-vendor.ps1",
                                    "sh": ["bash", "scripts/cache-vendor.sh"],
                                }
                            ]
                        },
                        "validate": {
                            "critical_wheels": [],
                            "critical_vendor": [
                                {"path": "vendor/VERSIONS", "label": "VERSIONS"}
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            cfg = load_config(root, config_file=cfg_path)
            self.assertEqual(len(cfg.after_cache_hooks), 1)
            self.assertEqual(cfg.after_cache_hooks[0].name, "vendor")
            self.assertEqual(cfg.after_cache_hooks[0].script, "scripts/cache-vendor.ps1")
            self.assertEqual(len(cfg.critical_vendor), 1)
            self.assertTrue(dockerfile_uses_vendor_mount(cfg))

    def test_resolve_script_ps1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = root / "scripts" / "cache-vendor.ps1"
            script.parent.mkdir(parents=True)
            script.write_text("# noop\n", encoding="utf-8")
            hook = CacheHook(name="vendor", script="scripts/cache-vendor.ps1")
            with mock.patch("offline_docker.hooks.os.name", "nt"):
                cmd = _resolve_command(hook, root)
            self.assertIsNotNone(cmd)
            assert cmd is not None
            self.assertEqual(cmd[0], "powershell")
            self.assertIn(str(script), cmd)

    def test_status_fails_without_vendor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text("name: t\n", encoding="utf-8")
            (root / "Dockerfile.offline").write_text(
                "RUN --mount=type=bind,from=oc,source=vendor,target=/vendor,ro true\n",
                encoding="utf-8",
            )
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "python": {"lock_files": []},
                        "dockerfiles": {"backend_offline": "Dockerfile.offline"},
                        "validate": {
                            "critical_wheels": [],
                            "critical_vendor": [
                                {"path": "vendor/VERSIONS", "label": "VERSIONS"}
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )
            # Minimal dirs so other checks don't drown the assertion
            oc = root / "offline-cache"
            for name in ("wheels", "debs", "npm", "docker"):
                (oc / name).mkdir(parents=True)
            for i in range(5):
                (oc / "debs" / f"p{i}.deb").write_bytes(b"x")
            (oc / "docker" / "ubuntu.tar").write_bytes(b"x")

            ctx = ProjectContext.load(root, config_file=cfg_path)
            report = collect_cache_status(ctx)
            vendor_errors = [
                i for i in report.items if i.level == "error" and "vendor" in i.label
            ]
            self.assertTrue(vendor_errors, report.items)
            self.assertFalse(report.ok)

    def test_run_after_cache_hooks_invokes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text("name: t\n", encoding="utf-8")
            script = root / "hook.py"
            script.write_text("print('ok')\n", encoding="utf-8")
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "python": {"lock_files": []},
                        "hooks": {
                            "after_cache": [
                                {"name": "demo", "run": ["python", "hook.py"]}
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )
            ctx = ProjectContext.load(root, config_file=cfg_path)
            with mock.patch("offline_docker.hooks.docker_cmd.run") as run:
                run.return_value = 0
                run_after_cache_hooks(ctx)
            self.assertTrue(run.called)
            args = run.call_args[0][0]
            self.assertEqual(args[0], "python")


if __name__ == "__main__":
    unittest.main()
