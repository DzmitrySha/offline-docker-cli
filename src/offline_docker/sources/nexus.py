"""Sonatype Nexus Repository source."""

from __future__ import annotations

from urllib.parse import urljoin

from offline_docker.sources.base import Ecosystem


class NexusSource:
    source_type = "nexus"

    def __init__(
        self,
        name: str = "nexus",
        *,
        url: str,
        repos: dict[str, str] | None = None,
        auth_env: str = "NEXUS_AUTH",
        enabled: bool = True,
        publish: bool = False,
        raw_repo: str | None = None,
    ) -> None:
        self.name = name
        self.url = url.rstrip("/")
        self.repos = dict(repos or {})
        self.auth_env = auth_env
        self.enabled = enabled and bool(url.strip())
        self.publish = publish
        self.raw_repo = raw_repo or self.repos.get("raw")

    def _repo_url(self, repo: str, suffix: str = "") -> str:
        base = f"{self.url}/repository/{repo.strip('/')}/"
        if not suffix:
            return base
        return urljoin(base, suffix.lstrip("/"))

    def index_urls(self, ecosystem: Ecosystem) -> list[str]:
        if not self.enabled:
            return []
        if ecosystem == "pypi":
            repo = self.repos.get("pypi")
            if not repo:
                return []
            return [self._repo_url(repo, "simple").rstrip("/") ]
        if ecosystem == "npm":
            repo = self.repos.get("npm")
            if not repo:
                return []
            return [self._repo_url(repo)]
        if ecosystem == "apt":
            repo = self.repos.get("apt") or self.repos.get("deb")
            if not repo:
                return []
            return [self._repo_url(repo)]
        return []

    def raw_base_url(self) -> str | None:
        if not self.enabled or not self.raw_repo:
            return None
        return self._repo_url(self.raw_repo)
