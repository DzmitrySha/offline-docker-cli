"""Регрессия гостевого скрипта download-npm-cache."""

from __future__ import annotations

import unittest

from offline_docker.download_npm import NPM_GUEST


class NpmGuestScriptTest(unittest.TestCase):
    def test_posix_sh_without_pipefail(self) -> None:
        # node:*-bookworm-slim: /bin/sh = dash, set -o pipefail недоступен.
        first = next(
            line.strip()
            for line in NPM_GUEST.splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        self.assertEqual(first, "set -eu")
        self.assertNotIn("pipefail", NPM_GUEST)
