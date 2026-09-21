"""CLI parsing tests (no Docker)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from offline_docker.cli import _resolve_action_name, parse_args
from offline_docker.actions import PROJECT_ACTIONS, resolve_action


class ParseArgsTest(unittest.TestCase):
    def test_cache_full(self) -> None:
        args = parse_args(["cache"])
        self.assertEqual(args.command, "cache")
        self.assertIsNone(getattr(args, "cache_cmd", None))
        self.assertEqual(_resolve_action_name(args), "cache")

    def test_cache_wheels(self) -> None:
        args = parse_args(["cache", "wheels"])
        self.assertEqual(args.cache_cmd, "wheels")
        self.assertEqual(_resolve_action_name(args), "cache-wheels")

    def test_cache_check_and_load(self) -> None:
        self.assertEqual(_resolve_action_name(parse_args(["cache", "check"])), "cache-check")
        self.assertEqual(_resolve_action_name(parse_args(["cache", "load"])), "cache-load")

    def test_build_targets(self) -> None:
        args = parse_args(["build", "base", "backend", "--no-cache"])
        self.assertEqual(args.command, "build")
        self.assertEqual(list(args.targets), ["base", "backend"])
        self.assertTrue(args.no_cache)

    def test_up_lab(self) -> None:
        args = parse_args(["up", "--lab", "frontend"])
        self.assertTrue(args.lab)
        self.assertFalse(args.online)
        self.assertEqual(list(args.services), ["frontend"])

    def test_up_online(self) -> None:
        args = parse_args(["up", "--online"])
        self.assertTrue(args.online)
        self.assertFalse(args.lab)

    def test_up_lab_online_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(["up", "--lab", "--online"])

    def test_down_lab_services(self) -> None:
        args = parse_args(["down", "--lab", "backend"])
        self.assertTrue(args.lab)
        self.assertEqual(list(args.services), ["backend"])
        self.assertEqual(_resolve_action_name(args), "down")

    def test_scan_short(self) -> None:
        args = parse_args(["scan", "backend"])
        self.assertEqual(args.target, "backend")
        self.assertIsNone(args.image)
        self.assertEqual(args.scanner, "trivy")

    def test_scan_trivy_explicit(self) -> None:
        args = parse_args(["scan", "trivy", "frontend", "myimg:1"])
        self.assertEqual(args.target, "frontend")
        self.assertEqual(args.image, "myimg:1")
        self.assertEqual(args.scanner, "trivy")

    def test_scan_bad_scanner(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(["scan", "grype", "backend"])

    def test_deprecated_alias_download(self) -> None:
        args = parse_args(["download-offline-cache"])
        self.assertEqual(_resolve_action_name(args), "cache")

    def test_deprecated_dev_up(self) -> None:
        args = parse_args(["dev-up", "--no-cache"])
        self.assertEqual(_resolve_action_name(args), "up-online")
        self.assertTrue(args.no_cache)

    def test_deprecated_scan(self) -> None:
        args = parse_args(["scan-trivy-offline", "backend"])
        self.assertEqual(_resolve_action_name(args), "scan")
        self.assertEqual(args.target, "backend")

    def test_version(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            parse_args(["-V"])
        self.assertEqual(ctx.exception.code, 0)


class ResolveActionTest(unittest.TestCase):
    def test_aliases_map(self) -> None:
        self.assertEqual(resolve_action("download-wheels"), "cache-wheels")
        self.assertEqual(resolve_action("build-offline"), "build")
        self.assertEqual(resolve_action("up-offline"), "up")
        self.assertEqual(resolve_action("dev-up"), "up-online")
        self.assertEqual(resolve_action("scan-trivy-offline"), "scan")
        self.assertEqual(resolve_action("down"), "down")

    def test_project_actions_include_new_and_old(self) -> None:
        self.assertIn("cache", PROJECT_ACTIONS)
        self.assertIn("download-offline-cache", PROJECT_ACTIONS)
        self.assertIn("down", PROJECT_ACTIONS)
        self.assertIn("up", PROJECT_ACTIONS)


class DownStackDispatchTest(unittest.TestCase):
    def test_down_calls_down_stack(self) -> None:
        from offline_docker.actions import run_action
        from offline_docker.context import ProjectContext
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text("name: t\n", encoding="utf-8")
            cfg = root / ".offline-docker.json"
            cfg.write_text(json.dumps({"compose_online": "docker-compose.yml"}), encoding="utf-8")
            ctx = ProjectContext.load(root, config_file=cfg)
            with patch("offline_docker.actions.down_stack") as mock_down:
                run_action("down", ctx, lab=True, services=["backend"])
                mock_down.assert_called_once()
                kwargs = mock_down.call_args.kwargs
                self.assertTrue(kwargs["lab"])
                self.assertFalse(kwargs["online"])
                self.assertEqual(kwargs["services"], ["backend"])


if __name__ == "__main__":
    unittest.main()
