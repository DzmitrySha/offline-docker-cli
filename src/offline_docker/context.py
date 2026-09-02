"""Runtime paths derived from ProjectConfig."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from offline_docker.config import ProjectConfig, load_config
from offline_docker.utils import combined_files_hash


@dataclass(frozen=True)
class ProjectContext:
    config: ProjectConfig
    wheels_dir: Path
    wheels_hash_file: Path
    debs_dir: Path
    apt_meta_dir: Path
    npm_cache_dir: Path
    docker_cache_dir: Path
    trivy_cache_dir: Path

    @property
    def root(self) -> Path:
        return self.config.root

    @property
    def offline_cache(self) -> Path:
        return self.config.offline_cache

    @property
    def log_dir(self) -> Path:
        return self.config.log_dir

    @classmethod
    def from_config(cls, config: ProjectConfig) -> ProjectContext:
        offline = config.offline_cache
        wheels = offline / "wheels"
        return cls(
            config=config,
            wheels_dir=wheels,
            wheels_hash_file=wheels / ".deps.sha256",
            debs_dir=offline / "debs",
            apt_meta_dir=offline / "apt-meta",
            npm_cache_dir=offline / "npm",
            docker_cache_dir=offline / "docker",
            trivy_cache_dir=offline / config.trivy.cache_subdir,
        )

    @classmethod
    def load(
        cls,
        root: Path,
        *,
        config_file: Path | None = None,
    ) -> ProjectContext:
        config = load_config(root, config_file=config_file)
        return cls.from_config(config)

    def ensure_offline_dirs(self) -> None:
        for d in (
            self.wheels_dir,
            self.debs_dir,
            self.apt_meta_dir,
            self.npm_cache_dir,
            self.docker_cache_dir,
            self.trivy_cache_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        from offline_docker.oc_discovery import discover_yarn_cache_specs

        for spec in discover_yarn_cache_specs(self.config):
            (self.offline_cache / spec.cache_subdir).mkdir(parents=True, exist_ok=True)
            (self.offline_cache / spec.archive_subdir).mkdir(parents=True, exist_ok=True)

    def ensure_log_dir(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def offline_build_log(self, stem: str) -> Path:
        self.ensure_log_dir()
        return self.log_dir / f"offline-build-{stem}.log"

    def trivy_scan_log(self, target: str) -> Path:
        self.ensure_log_dir()
        return self.log_dir / f"trivy-scan-{target}.log"

    def python_deps_hash(self) -> str:
        paths = self.config.python_lock_paths()
        if not paths:
            raise RuntimeError("Python lock files not found")
        return combined_files_hash(paths)

    def set_offline_cache_env(self) -> None:
        import os

        os.environ.setdefault("DOCKER_BUILDKIT", "1")
        os.environ.setdefault("OFFLINE_CACHE", str(self.offline_cache))
