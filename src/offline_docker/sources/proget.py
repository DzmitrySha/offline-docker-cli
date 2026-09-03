"""Inedo ProGet feed source."""

from __future__ import annotations

from offline_docker.sources.base import Ecosystem


class ProGetSource:
    source_type = "proget"

    def __init__(
        self,
        name: str = "proget",
        *,
        url: str,
        feeds: dict[str, str] | None = None,
        auth_env: str = "PROGET_API_KEY",
        enabled: bool = True,
        publish: bool = False,
    ) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self.feeds = dict(feeds or {})
        self.auth_env = auth_env
        self.enabled = enabled and bool(url.strip())
        self.publish = publish

    def index_urls(self, ecosystem: Ecosystem) -> list[str]:
        if not self.enabled:
            return []
        if ecosystem == "pypi":
            feed = self.feeds.get("pypi")
            if not feed:
                return []
            return [f"{self.url}/pypi/{feed}/simple"]
        if ecosystem == "npm":
            feed = self.feeds.get("npm")
            if not feed:
                return []
            return [f"{self.url}/npm/{feed}/"]
        if ecosystem == "apt":
            feed = self.feeds.get("deb") or self.feeds.get("apt")
            if not feed:
                return []
            return [f"{self.url}/debian/{feed}/"]
        return []

    def universal_feed(self) -> str | None:
        return self.feeds.get("universal") or self.feeds.get("asset")
