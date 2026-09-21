"""Tests for stale wheel pruning against exact requirement pins."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from offline_docker.wheel_prune import (
    parse_exact_pins,
    parse_wheel_name_version,
    prune_stale_wheels,
)


class ParsePinsTest(unittest.TestCase):
    def test_exact_pins(self) -> None:
        text = """
# comment
protobuf==7.36.2
requests==2.32.3 ; python_version >= "3.10"
-e .
flex
numpy>=1.0
"""
        pins = parse_exact_pins(text)
        self.assertEqual(pins["protobuf"], "7.36.2")
        self.assertEqual(pins["requests"], "2.32.3")
        self.assertNotIn("numpy", pins)

    def test_wheel_name(self) -> None:
        self.assertEqual(
            parse_wheel_name_version(
                "protobuf-6.32.0-cp39-abi3-manylinux2014_x86_64.whl"
            ),
            ("protobuf", "6.32.0"),
        )
        self.assertEqual(
            parse_wheel_name_version("protobuf-7.36.2-py3-none-any.whl"),
            ("protobuf", "7.36.2"),
        )


class PruneStaleTest(unittest.TestCase):
    def test_removes_mismatched_protobuf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wheels = Path(tmp) / "wheels"
            wheels.mkdir()
            stale = wheels / "protobuf-6.32.0-cp39-abi3-manylinux2014_x86_64.whl"
            stale.write_bytes(b"x")
            other = wheels / "propcache-0.3.2-py3-none-any.whl"
            other.write_bytes(b"y")
            req = Path(tmp) / "req.txt"
            req.write_text("protobuf==7.36.2\npropcache==0.3.2\n", encoding="utf-8")

            deleted = prune_stale_wheels(req, wheels)
            self.assertEqual(deleted, [stale.name])
            self.assertFalse(stale.exists())
            self.assertTrue(other.exists())

    def test_keeps_matching_drops_other_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wheels = Path(tmp) / "wheels"
            wheels.mkdir()
            good = wheels / "protobuf-7.36.2-py3-none-any.whl"
            old = wheels / "protobuf-6.32.0-py3-none-any.whl"
            good.write_bytes(b"a")
            old.write_bytes(b"b")
            req = Path(tmp) / "req.txt"
            req.write_text("protobuf==7.36.2\n", encoding="utf-8")

            deleted = prune_stale_wheels(req, wheels)
            self.assertEqual(deleted, [old.name])
            self.assertTrue(good.exists())


if __name__ == "__main__":
    unittest.main()
