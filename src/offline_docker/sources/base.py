"""Package source protocol."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

Ecosystem = Literal["pypi", "npm", "apt"]


@runtime_checkable
class PackageSource(Protocol):
    name: str
    source_type: str
    enabled: bool

    def index_urls(self, ecosystem: Ecosystem) -> list[str]:
        """Ordered index/registry URLs for the ecosystem (may be empty)."""
        ...
