"""Discovery of yarn / oc archive requirements from Dockerfiles."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from offline_docker.config import load_config
from offline_docker.oc_discovery import (
    discover_yarn_cache_specs,
    resolve_build_arg,
    yarn_cache_needed,
)

_OFFLINE_DOCKERFILE = """\
ARG ANYTHINGLLM_VERSION=1.15.0
FROM node:18-slim AS frontend-build
ARG ANYTHINGLLM_VERSION
WORKDIR /upstream
RUN --mount=type=bind,from=oc,source=archives,target=/oc-archives,ro \\
    tar -xzf "/oc-archives/upstream-v${ANYTHINGLLM_VERSION}.tar.gz" -C /upstream --strip-components=1
WORKDIR /upstream/frontend
RUN --mount=type=bind,from=oc,source=yarn,target=/yarn-cache,ro \\
    yarn install --offline
"""

_ONLINE_DOCKERFILE = """\
ARG ANYTHINGLLM_VERSION=2.0.0
FROM node:20-slim AS frontend-build
ARG ANYTHINGLLM_VERSION
RUN git clone --depth 1 --branch "v${ANYTHINGLLM_VERSION}" \\
    https://example.com/app.git /upstream
WORKDIR /upstream/frontend
"""


class OcDiscoveryTest(unittest.TestCase):
    def _make_project(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "docker-compose.yml").write_text("name: test\n", encoding="utf-8")
        docker = root / "docker"
        docker.mkdir()
        (docker / "service.Dockerfile.offline").write_text(_OFFLINE_DOCKERFILE, encoding="utf-8")
        (docker / "service.Dockerfile").write_text(_ONLINE_DOCKERFILE, encoding="utf-8")
        (root / ".offline-docker.json").write_text("{}", encoding="utf-8")
        return root

    def test_discover_yarn_cache_from_dockerfile(self) -> None:
        root = self._make_project()
        cfg = load_config(root)
        specs = discover_yarn_cache_specs(cfg)
        self.assertEqual(len(specs), 1)
        spec = specs[0]
        self.assertEqual(spec.cache_subdir, "yarn")
        self.assertEqual(spec.archive_subdir, "archives")
        self.assertEqual(spec.version_arg, "ANYTHINGLLM_VERSION")
        self.assertEqual(spec.git_url, "https://example.com/app.git")
        self.assertTrue(yarn_cache_needed(cfg))

    def test_resolve_build_arg_from_dockerfile(self) -> None:
        root = self._make_project()
        cfg = load_config(root)
        spec = discover_yarn_cache_specs(cfg)[0]
        version = resolve_build_arg(cfg, spec.version_arg, cfg.path(spec.source_dockerfile))
        self.assertEqual(version, "1.15.0")


if __name__ == "__main__":
    unittest.main()
