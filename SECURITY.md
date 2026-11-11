# Security policy

## Threat model

`offdock` splits work between two kinds of machines:

- a CI runner or developer machine **with network access** fills the offline cache (`cache`);
- an **offline machine** loads and builds images from that cache (`cache load`, `build`, `up`, `scan`).

The trust boundary is the target repository and the transferable `offline-cache/` directory. Anything that enters the cache is later executed or built on the offline machine.

## What is protected and how

- Registry tokens are read **only from environment variables** (`PROGET_API_KEY`, `NEXUS_AUTH`). The user-level `sources.json` and the project `.offline-docker.json` store only the environment variable **name** (`auth_env`), never the value (`configure.py`, `resolve.py`).
- Nexus authentication: `user:pass` is sent as Basic, any other value as Bearer (`nexus_client.py`).
- Trivy scans run from the cached DB; scanning does not require network access.

## Cache integrity

- `cache check` verifies that artifacts are present; it does **not** verify signatures or checksums.
- Images are pulled **by tag** and archived with `docker save` (`download_images.py`). For strict verification, pin image digests in `docker_images`.
- The Trivy DB ages; `db_max_age_days` only emits a warning and never blocks a build or scan (`trivy_scan.py`).

## Required practices

- Use only trusted target repositories — their config drives what is downloaded and what hooks run.
- Prefer HTTPS for ProGet/Nexus. Over plain HTTP, pip receives `--trusted-host` and npm gets `strict-ssl false`, which lowers TLS verification.
- Use short-lived registry tokens and rotate them.
- Refresh the Trivy DB on a machine with network access before transferring the bundle.
- Pin image digests in `docker_images` when reproducibility and integrity matter.

## Residual risks

- `hooks.after_cache` executes win/sh/script hooks from the target repository with the current user's privileges — arbitrary code execution by design.
- The cache is not signed: a compromised upstream or registry can deliver malicious artifacts.
- Scanning covers Docker images only; wheels, npm packages and debs are not scanned by `offdock`.

## Incident response

1. Stop the affected pipeline and do not build from the suspect cache.
2. Revoke and rotate `PROGET_API_KEY` / `NEXUS_AUTH`.
3. Delete and repopulate `offline-cache/` from a trusted source.
4. Verify images by digest.
5. Review `hooks.after_cache` scripts and the target repository history.

## Reporting a vulnerability

Report privately through GitHub Security Advisories in the public repository, the corporate GitLab (confidential issue), or by email to `d.shapovalov@vitebsk.energo.net`.
Do **not** open a public issue for a vulnerability.
