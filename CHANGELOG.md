# Changelog

### 2.2.3

- The PyPI distribution has been renamed to `offdock`: install with `pip install offdock`. The import package (`offline_docker`), the `offdock` entry point, and `.offline-docker.json` are unchanged.
- Remove the old distribution before upgrading: `pip uninstall offline-docker-cli`.

### 2.2.2

- `cache debs`: the cache is bound to the guest image distribution — `debs/.base-os` stores `<ID>-<VERSION_ID>`; when the base changes (for example, `python:3.12-slim` bookworm → trixie), stale `.deb` files are removed automatically instead of mixing Ubuntu/Debian packages.

### 2.2.1

- `cache wheels`: Python is taken from the base image (`debs.ubuntu_image`) instead of being installed via apt. Packages `python3.12*` are missing in Debian 13 (trixie), which made `python:3.12-slim` fail on `apt-get install` and wheels were not downloaded.
- ABI check: if the image Python is older than the project's `requires-python`, `cache wheels` fails with an explicit error instead of producing wheels for a foreign version.

### 2.2.0

- `hooks.after_cache` in `.offline-docker.json`: win/sh/script hooks after `cache` / before the offline build (vendor binaries etc.).
- `validation.critical_vendor` — validation of critical vendor artifacts in the cache status.
- `AGENTS.md` — rules for agents working with the CLI.

### 2.1.0

- Removed deprecated aliases of old subcommands (`download-*`, `build-offline`, `up-offline`, `dev-up`, `scan-trivy-offline`, …).
- Removed the `offline-docker` entrypoint from `pyproject.toml` — only `offdock` remains.

### 2.0.0

- **`offdock`** binary.
- Short commands: `cache` (+ subcommands), `build`, `up`, `down`, `scan [trivy]`.
- `up --online` instead of `dev-up`; `up --lab` keeps its meaning.
- New `down` command with the same modes and service support.

### 1.4.2

- `configure --with-upstream`: an explicit local + PyPI/npmjs mode for populating the cache from the network.
- Empty ProGet/Nexus URLs no longer silently write local-only — the default is `local,upstream`.
- `download-wheels`: WARN on local-only fallback; prune stale wheels by pin; retry without `--find-links`; `--retries`/`--timeout`.
- `download-npm-cache`: WARN when the registry falls back to the default under local-only.

### 1.4.1

- `download-npm-cache`: the guest script in `node:*-slim` runs through `/bin/sh` (dash) — no `set -o pipefail` (otherwise `Illegal option -o pipefail`).
- `offline-docker --version` / `-V`; `__version__` synchronized with `pyproject.toml`.

### 1.4.0

- Optional Textual TUI: `offline-docker tui` (`pip install -e ".[tui]"`) — cache status, command menu, live log.
- Shared `actions` / structured `collect_cache_status` layer for the CLI and TUI.

### 1.3.0

- Multi-source packages: local → ProGet → Nexus (order in `resolve.order`).
- `offline-docker configure` command (user-level `sources.json`; empty URLs = local-only).
- `download-wheels` / `download-npm-cache` / `download-debs` use the index URL chain.
- Best-effort materialize/publish for Nexus raw and ProGet universal (`publish: true`).
- `discover` prints the active sources.

### 1.2.0

- `images` schema: canonical fields `base`, `backend`, `frontend` (a single `cuda12` / `latest` tag for online and offline).
- Removed `legacy_base_*` and retagging of old images.
- Old JSON (`base_online`, `backend_offline`, …) is read when loading the config.
