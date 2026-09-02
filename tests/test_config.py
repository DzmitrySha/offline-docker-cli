"""Config loading tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from offline_docker.config import load_config


class LoadConfigImagesTest(unittest.TestCase):
    def test_new_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text(
                "name: test\nservices:\n  backend:\n    image: test-backend:latest\n",
                encoding="utf-8",
            )
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "images": {
                            "base": "neuroai-base:cuda12",
                            "backend": "test-backend:latest",
                            "frontend": "test-frontend:latest",
                        }
                    }
                ),
                encoding="utf-8",
            )
            cfg = load_config(root, config_file=cfg_path)
            self.assertEqual(cfg.images.base, "neuroai-base:cuda12")
            self.assertEqual(cfg.images.backend, "test-backend:latest")
            self.assertEqual(cfg.images.frontend, "test-frontend:latest")

    def test_legacy_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text("name: test\n", encoding="utf-8")
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "images": {
                            "base_online": "neuroai-base:cuda12",
                            "base_offline": "neuroai-base:offline",
                            "backend_offline": "test-backend:offline",
                            "frontend_offline": "test-frontend:offline",
                        }
                    }
                ),
                encoding="utf-8",
            )
            cfg = load_config(root, config_file=cfg_path)
            self.assertEqual(cfg.images.base, "neuroai-base:cuda12")
            self.assertEqual(cfg.images.backend, "test-backend:latest")
            self.assertEqual(cfg.images.frontend, "test-frontend:latest")

    def test_python_uv_export_prune(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text("name: test\n", encoding="utf-8")
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "python": {
                            "uv_export_prune": ["torch", "neuralprophet"],
                            "extra_wheel_specs": ["neuralprophet[live]==0.9.0"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            cfg = load_config(root, config_file=cfg_path)
            self.assertEqual(cfg.uv_export_prune, ["torch", "neuralprophet"])
            self.assertEqual(cfg.extra_wheel_specs, ["neuralprophet[live]==0.9.0"])

    def test_build_services_arbitrary_compose_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text("name: test\n", encoding="utf-8")
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "build_services": [
                            "base",
                            "backend",
                            "frontend",
                            "worker",
                            "ocr-server",
                        ]
                    }
                ),
                encoding="utf-8",
            )
            cfg = load_config(root, config_file=cfg_path)
            self.assertEqual(
                cfg.build_services,
                ["base", "backend", "frontend", "worker", "ocr-server"],
            )

    def test_python_project_dir_from_lock_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backend = root / "backend"
            backend.mkdir()
            (backend / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            (backend / "uv.lock").write_text("", encoding="utf-8")
            (root / "docker-compose.yml").write_text("name: test\n", encoding="utf-8")
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "python": {
                            "lock_files": [
                                "backend/pyproject.toml",
                                "backend/uv.lock",
                            ]
                        }
                    }
                ),
                encoding="utf-8",
            )
            cfg = load_config(root, config_file=cfg_path)
            self.assertEqual(cfg.effective_python_project_dir(), "backend")
            self.assertTrue(cfg.use_uv_export)

    def test_python_project_dir_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            (root / "uv.lock").write_text("", encoding="utf-8")
            (root / "docker-compose.yml").write_text("name: test\n", encoding="utf-8")
            cfg = load_config(root)
            self.assertEqual(cfg.effective_python_project_dir(), ".")
            self.assertTrue(cfg.use_uv_export)

    def test_use_uv_export_respects_explicit_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            (root / "uv.lock").write_text("", encoding="utf-8")
            (root / "docker-compose.yml").write_text("name: test\n", encoding="utf-8")
            cfg_path = root / ".offline-docker.json"
            cfg_path.write_text(json.dumps({"use_uv_export": False}), encoding="utf-8")
            cfg = load_config(root, config_file=cfg_path)
            self.assertFalse(cfg.use_uv_export)


if __name__ == "__main__":
    unittest.main()
