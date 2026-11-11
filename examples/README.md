# `.offline-docker.json` template

A universal example for any Docker project (backend + frontend, slim CUDA base, offline cache).

<sub>English · <a href="../docs/ru/examples.md">Русская версия</a></sub>

## Install into a project

```bash
# Option A: auto-generated draft (recursive scan + gaps)
offdock init -p /path/to/your-project

# Option B: manual template
cp examples/offline-docker.json.example /path/to/your-project/.offline-docker.json
```

If `.offline-docker.json` already exists, `init` writes `.offline-docker.generated.json` and does not overwrite the canonical file.

Then edit it for your repository:

| Field | What to replace |
|-------|-----------------|
| `app_name` | short application name (for the `{APP_NAME}_OFFLINE_CACHE` env) |
| `images.base` | shared base (`neuroai-base:cuda12`) |
| `images.backend` / `images.frontend` | app image tags (`*:latest`) |
| `debs.packages` | APT packages from `Dockerfile.base` / `Dockerfile` |
| `debs.extra_repos` | if needed (e.g. Microsoft ODBC) |
| `docker_images` | base images for `docker load` (redis, trivy, etc.) |
| `validate.critical_wheels` | required wheels for validation |
| `compose_up_offline_lab` | remove if there is no `docker-compose.lab.yml` |
| `build_services` | service names for `build`: `base` (separate build) and any keys from the merged compose files |

## Check

```bash
offdock discover -p /path/to/your-project
```

## Config sections

- **compose_build** — merge files for `build`
- **compose_up_offline** — merge files for `up`
- **build_services** — the list used by `build` without arguments: `base` + service names from compose (not only backend/frontend)
- **compose_up_offline_lab** — same + `docker-compose.lab.yml` (`up --lab` flag)

If `compose_up_offline` is not set, the CLI falls back to `compose_build`.

### Home lab (`--lab`)

1. Create `docker-compose.lab.yml` in the project root (ports, volumes, traefik, etc.).
2. Set `compose_up_offline_lab` — the `-f` file order for `docker compose up`.
3. Run: `offdock up -p . --lab`

If `compose_up_offline_lab` is empty, the CLI takes the list from `compose_up_offline` and appends `docker-compose.lab.yml`.

### Trivy (`trivy`)

The section affects `cache trivy` and `scan` / `scan trivy`:

| Field | Purpose |
|-------|---------|
| `scanner_image` | Trivy image (must be present in `docker_images`) |
| `db_max_age_days` | When the DB is considered stale |
| `severity` | Scan filter (`HIGH,CRITICAL`) |
| `scanners` | Scanner types (`vuln`, `secret`, …) |

The scan command requires a target `backend` or `frontend`:

```bash
offdock scan backend
offdock scan trivy frontend myapp-frontend:custom-tag
```

The image for the scan comes from `images.backend` / `images.frontend` unless a tag is passed.

### Package sources (`cache`) — optional

The section is **not required** in the project config. By default, sources are configured once per machine:

```bash
offdock configure
```

If a project-specific chain is needed (it overrides the user config), add a neutral block with **empty** URLs or your own values:

```json
"cache": {
  "sources": [
    { "name": "local", "type": "filesystem", "enabled": true },
    {
      "name": "proget",
      "type": "proget",
      "url": "",
      "feeds": { "pypi": "", "npm": "", "deb": "" },
      "enabled": false
    },
    {
      "name": "nexus",
      "type": "nexus",
      "url": "",
      "repos": { "pypi": "", "npm": "" },
      "enabled": false
    }
  ],
  "resolve": {
    "order": ["local"],
    "fill_local": true,
    "on_miss": "fail"
  }
}
```

Empty URLs / `enabled: false` mean offline cache only. Corporate addresses are **not** included in this example — see `offdock configure --help`.
