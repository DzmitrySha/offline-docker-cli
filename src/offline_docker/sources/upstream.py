"""Public upstream registries (PyPI / npmjs)."""

from __future__ import annotations

from offline_docker.sources.base import Ecosystem


class UpstreamSource:
    source_type = "upstream"

    def __init__(
        self,
        name: str = "upstream",
        *,
        enabled: bool = False,
        pypi_index: str = "https://pypi.org/simple",
        npm_registry: str = "https://registry.npmjs.org/",
        pytorch_index: str | None = None,
    ) -> None:
        self.name = name
        self.enabled = enabled
        self.pypi_index = pypi_index.rstrip("/")
        self.npm_registry = npm_registry.rstrip("/") + "/"
        self.pytorch_index = pytorch_index.rstrip("/") if pytorch_index else None

    def index_urls(self, ecosystem: Ecosystem) -> list[str]:
        if not self.enabled:
            return []
        if ecosystem == "pypi":
            urls = [self.pypi_index]
            if self.pytorch_index:
                urls.append(self.pytorch_index)
            return urls
        if ecosystem == "npm":
            return [self.npm_registry]
        return []
