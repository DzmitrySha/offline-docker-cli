"""Local offline-cache filesystem source."""

from __future__ import annotations

from offline_docker.sources.base import Ecosystem


class FilesystemSource:
    source_type = "filesystem"

    def __init__(self, name: str = "local", *, enabled: bool = True) -> None:
        self.name = name
        self.enabled = enabled

    def index_urls(self, ecosystem: Ecosystem) -> list[str]:
        # Local is consumed via --find-links / npm cache mount, not HTTP indexes.
        return []
