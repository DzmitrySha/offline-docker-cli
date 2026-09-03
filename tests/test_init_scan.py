"""Tests for recursive scan and offline-docker init."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from offline_docker.init_cmd import run_init
from offline_docker.scan import (
    compute_init_gaps,
    inventory_to_draft_config,
    recursive_scan,
    resolve_init_output_path,
)


def _touch(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class RecursiveScanTest(unittest.TestCase):
    def test_finds_nested_and_skips_node_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "Dockerfile", "FROM ubuntu:24.04\n")
            _touch(root / "apps" / "web" / "package-lock.json", "{}")
            _touch(root / "apps" / "web" / "package.json", "{}")
            _touch(root / "services" / "api" / "pyproject.toml", "[project]\nname='api'\n")
            _touch(
                root / "node_modules" / "left-pad" / "package.json",
                '{"name":"left-pad"}',
            )
            _touch(root / "apps" / "web" / "node_modules" / "x" / "package.json", "{}")

            inv = recursive_scan(root)
            self.assertIn("apps/web/package-lock.json", inv.frontend_lock_paths)
            self.assertIn("services/api/pyproject.toml", inv.python_files)
            self.assertIn("Dockerfile", inv.dockerfiles)
            self.assertNotIn("node_modules/left-pad", " ".join(inv.package_json_dirs))
            self.assertTrue(
                all("node_modules" not in p for p in inv.package_json_dirs)
            )
            self.assertTrue(
                all("node_modules" not in p for p in inv.frontend_lock_paths)
            )

            cfg = inventory_to_draft_config(root, inv)
            self.assertEqual(cfg.frontend_dir, "apps/web")
            self.assertEqual(cfg.frontend_lock, "package-lock.json")
            self.assertIn("services/api/pyproject.toml", cfg.python_lock_files)

            gaps = compute_init_gaps(cfg, inv)
            joined = "\n".join(gaps)
            self.assertIn("Dockerfile.offline", joined)
            self.assertIn("offline", joined.lower())


class InitCommandTest(unittest.TestCase):
    def test_writes_canonical_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "Dockerfile", "FROM ubuntu:24.04\nRUN apt-get install -y curl\n")
            _touch(root / "frontend" / "package-lock.json", "{}")
            out = run_init(root)
            self.assertEqual(out.name, ".offline-docker.json")
            self.assertTrue(out.is_file())
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["frontend"]["dir"], "frontend")
            self.assertIn("_init", data)
            self.assertIn("gaps", data["_init"])
            self.assertTrue(any("offline" in g.lower() for g in data["_init"]["gaps"]))

    def test_writes_generated_when_canonical_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "Dockerfile", "FROM alpine:3.20\n")
            canon = root / ".offline-docker.json"
            canon.write_text('{"app_name": "userapp"}\n', encoding="utf-8")
            original = canon.read_text(encoding="utf-8")

            out = run_init(root)
            self.assertEqual(out.name, ".offline-docker.generated.json")
            self.assertTrue(out.is_file())
            self.assertEqual(canon.read_text(encoding="utf-8"), original)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["_init"]["output"], ".offline-docker.generated.json")

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _touch(root / "Dockerfile", "FROM ubuntu:24.04\n")
            out = run_init(root, dry_run=True)
            self.assertEqual(out.name, ".offline-docker.json")
            self.assertFalse(out.is_file())
            self.assertIsNone(
                next(root.glob(".offline-docker*.json"), None)
            )

    def test_resolve_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(
                resolve_init_output_path(root).name, ".offline-docker.json"
            )
            (root / ".offline-docker.yaml").write_text("app_name: x\n", encoding="utf-8")
            self.assertEqual(
                resolve_init_output_path(root).name,
                ".offline-docker.generated.json",
            )


if __name__ == "__main__":
    unittest.main()
