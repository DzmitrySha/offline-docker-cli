"""Tests for user-level sources config and PackageResolver."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from offline_docker.configure import run_configure
from offline_docker.resolve import (
    PackageResolver,
    merge_cache_settings,
    pip_index_chain_for_download,
    sources_from_cache_dict,
)
from offline_docker.sources.nexus import NexusSource
from offline_docker.sources.proget import ProGetSource
from offline_docker.user_config import online_fill_dict, save_user_sources


class ResolveOrderTest(unittest.TestCase):
    def test_local_only_default(self) -> None:
        settings = merge_cache_settings(
            user_data=None,
            project_data=None,
            pypi_index="https://pypi.org/simple",
            pytorch_index="https://download.pytorch.org/whl/cu128",
        )
        resolver = PackageResolver(settings)
        self.assertTrue(resolver.is_local_only())
        self.assertEqual(resolver.pypi_index_chain(), [])
        self.assertEqual(settings.resolve.order, ["local"])

    def test_proget_then_nexus_order(self) -> None:
        data = {
            "sources": [
                {"name": "local", "type": "filesystem"},
                {
                    "name": "proget",
                    "type": "proget",
                    "url": "https://proget.example.com",
                    "feeds": {"pypi": "ve_pypi", "npm": "npm-ve"},
                    "enabled": True,
                },
                {
                    "name": "nexus",
                    "type": "nexus",
                    "url": "http://nexus.example.com:8081",
                    "repos": {"pypi": "pypi-group", "npm": "npm-group"},
                    "enabled": True,
                },
            ],
            "resolve": {"order": ["local", "proget", "nexus"], "fill_local": True},
        }
        settings = sources_from_cache_dict(data)
        resolver = PackageResolver(settings)
        chain = resolver.pypi_index_chain()
        self.assertEqual(
            chain,
            [
                "https://proget.example.com/pypi/ve_pypi/simple",
                "http://nexus.example.com:8081/repository/pypi-group/simple",
            ],
        )
        self.assertEqual(
            resolver.primary_npm_registry(),
            "https://proget.example.com/npm/npm-ve/",
        )

    def test_project_cache_overrides_user(self) -> None:
        user = {
            "sources": [
                {"name": "local", "type": "filesystem"},
                {
                    "name": "proget",
                    "type": "proget",
                    "url": "https://proget.user",
                    "feeds": {"pypi": "ve_pypi"},
                    "enabled": True,
                },
            ],
            "resolve": {"order": ["local", "proget"]},
        }
        project = {
            "sources": [
                {"name": "local", "type": "filesystem"},
                {
                    "name": "nexus",
                    "type": "nexus",
                    "url": "http://nexus.project:8081",
                    "repos": {"pypi": "pypi-group"},
                    "enabled": True,
                },
            ],
            "resolve": {"order": ["local", "nexus"]},
        }
        settings = merge_cache_settings(
            user_data=user,
            project_data=project,
            pypi_index="https://pypi.org/simple",
            pytorch_index="https://download.pytorch.org/whl/cu128",
        )
        self.assertEqual(settings.cache_config_origin, "project")
        resolver = PackageResolver(settings)
        self.assertEqual(
            resolver.pypi_index_chain(),
            ["http://nexus.project:8081/repository/pypi-group/simple"],
        )

    def test_env_order_override(self) -> None:
        data = {
            "sources": [
                {"name": "local", "type": "filesystem"},
                {
                    "name": "proget",
                    "type": "proget",
                    "url": "https://proget.example.com",
                    "feeds": {"pypi": "ve_pypi"},
                    "enabled": True,
                },
                {
                    "name": "nexus",
                    "type": "nexus",
                    "url": "http://nexus.example.com:8081",
                    "repos": {"pypi": "pypi-group"},
                    "enabled": True,
                },
            ],
            "resolve": {"order": ["local", "proget", "nexus"]},
        }
        with mock.patch.dict(os.environ, {"OFFLINE_RESOLVE_ORDER": "local,nexus"}):
            settings = merge_cache_settings(
                user_data=data,
                project_data=None,
                pypi_index="https://pypi.org/simple",
                pytorch_index="https://download.pytorch.org/whl/cu128",
            )
        resolver = PackageResolver(settings)
        self.assertEqual(
            resolver.pypi_index_chain(),
            ["http://nexus.example.com:8081/repository/pypi-group/simple"],
        )


class ConfigureNonInteractiveTest(unittest.TestCase):
    def _ns(self, **kwargs: object) -> mock.Mock:
        base = dict(
            local_only=False,
            with_upstream=False,
            non_interactive=True,
            proget_url=None,
            nexus_url=None,
            proget_pypi=None,
            proget_npm=None,
            proget_deb=None,
            nexus_pypi=None,
            nexus_npm=None,
            nexus_raw=None,
            order=None,
        )
        base.update(kwargs)
        return mock.Mock(**base)

    def test_local_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"OFFLINE_DOCKER_CONFIG_DIR": tmp}):
                run_configure(self._ns(local_only=True))
                path = Path(tmp) / "sources.json"
                self.assertTrue(path.is_file())
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(data["resolve"]["order"], ["local"])

    def test_with_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"OFFLINE_DOCKER_CONFIG_DIR": tmp}):
                run_configure(self._ns(with_upstream=True))
                data = json.loads((Path(tmp) / "sources.json").read_text(encoding="utf-8"))
                self.assertEqual(data["resolve"]["order"], ["local", "upstream"])
                settings = merge_cache_settings(
                    user_data=data,
                    project_data=None,
                    pypi_index="https://pypi.org/simple",
                    pytorch_index="https://download.pytorch.org/whl/cu128",
                )
                resolver = PackageResolver(settings)
                self.assertFalse(resolver.is_local_only())
                self.assertIn("pypi.org", resolver.pypi_index_chain()[0])

    def test_empty_urls_default_to_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"OFFLINE_DOCKER_CONFIG_DIR": tmp}):
                run_configure(self._ns())
                data = json.loads((Path(tmp) / "sources.json").read_text(encoding="utf-8"))
                self.assertEqual(data, online_fill_dict())

    def test_both_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"OFFLINE_DOCKER_CONFIG_DIR": tmp}):
                run_configure(
                    self._ns(
                        proget_url="https://proget.vitebsk.energo.net",
                        nexus_url="http://repos.vitebsk.energo.by:8081",
                        proget_pypi="ve_pypi",
                        proget_npm="npm-ve",
                        proget_deb="local-deb",
                        nexus_pypi="pypi-group",
                        nexus_npm="npm-group",
                        order="local,proget,nexus",
                    )
                )
                data = json.loads((Path(tmp) / "sources.json").read_text(encoding="utf-8"))
                self.assertEqual(data["resolve"]["order"], ["local", "proget", "nexus"])
                settings = sources_from_cache_dict(data)
                resolver = PackageResolver(settings)
                self.assertIn("ve_pypi", resolver.pypi_index_chain()[0])
                self.assertIn("pypi-group", resolver.pypi_index_chain()[1])
                self.assertTrue(any(isinstance(s, ProGetSource) for s in resolver.sources()))
                self.assertTrue(any(isinstance(s, NexusSource) for s in resolver.sources()))


class DownloadIndexFallbackTest(unittest.TestCase):
    def test_local_only_fallback_chain(self) -> None:
        settings = merge_cache_settings(
            user_data=None,
            project_data=None,
            pypi_index="https://pypi.org/simple",
            pytorch_index="https://download.pytorch.org/whl/cu128",
        )
        resolver = PackageResolver(settings)
        chain, fallback = pip_index_chain_for_download(
            resolver,
            pypi_index="https://pypi.org/simple",
            pytorch_index="https://download.pytorch.org/whl/cu128",
        )
        self.assertTrue(fallback)
        self.assertEqual(
            chain,
            [
                "https://pypi.org/simple",
                "https://download.pytorch.org/whl/cu128",
            ],
        )

    def test_upstream_no_fallback(self) -> None:
        settings = merge_cache_settings(
            user_data=online_fill_dict(),
            project_data=None,
            pypi_index="https://pypi.org/simple",
            pytorch_index="https://download.pytorch.org/whl/cu128",
        )
        resolver = PackageResolver(settings)
        chain, fallback = pip_index_chain_for_download(
            resolver,
            pypi_index="https://pypi.org/simple",
            pytorch_index="https://download.pytorch.org/whl/cu128",
        )
        self.assertFalse(fallback)
        self.assertEqual(chain[0], "https://pypi.org/simple")
        self.assertIn("pytorch.org", chain[1])


class LoadConfigCacheMergeTest(unittest.TestCase):
    def test_load_config_picks_user_sources(self) -> None:
        from offline_docker.config import load_config

        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / "cfg"
            cfg_dir.mkdir()
            save_path = cfg_dir / "sources.json"
            with mock.patch.dict(os.environ, {"OFFLINE_DOCKER_CONFIG_DIR": str(cfg_dir)}):
                save_user_sources(
                    {
                        "sources": [
                            {"name": "local", "type": "filesystem"},
                            {
                                "name": "proget",
                                "type": "proget",
                                "url": "https://proget.example.com",
                                "feeds": {"pypi": "ve_pypi", "npm": "npm-ve"},
                                "enabled": True,
                            },
                        ],
                        "resolve": {"order": ["local", "proget"]},
                    }
                )
                root = Path(tmp) / "proj"
                root.mkdir()
                (root / "docker-compose.yml").write_text("name: t\n", encoding="utf-8")
                cfg = load_config(root)
                self.assertEqual(cfg.cache_config_origin, "user")
                chain = cfg.package_resolver().pypi_index_chain()
                self.assertEqual(chain[0], "https://proget.example.com/pypi/ve_pypi/simple")
                self.assertTrue(save_path.is_file())


if __name__ == "__main__":
    unittest.main()
