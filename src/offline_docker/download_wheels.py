"""Download Linux wheels into offline-cache/wheels."""

from __future__ import annotations

import os
from pathlib import Path

from offline_docker import docker_cmd
from offline_docker.context import ProjectContext
from offline_docker.utils import docker_mount_path


WHEELS_GUEST_UV = r"""
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl build-essential pkg-config cython3 \
  ffmpeg libavformat-dev libavcodec-dev libavdevice-dev \
  libavutil-dev libavfilter-dev libswscale-dev libswresample-dev
rm -rf /var/lib/apt/lists/*

# Python берём из базового образа (python:3.12-slim и т.п.): его версия задаёт
# ABI скачанных wheel-ов. Пакеты python3.12* из apt ставить нельзя — в Debian 13
# (trixie) их нет, там python3 = 3.13. apt-пакеты python3* нужны только когда
# интерпретатора/venv в образе нет (ubuntu:24.04, debian:bookworm-slim).
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import venv, ensurepip' >/dev/null 2>&1; then
  echo ">>> python3/venv в образе нет — ставим из apt"
  apt-get update
  apt-get install -y --no-install-recommends python3 python3-venv python3-dev python3-pip
  rm -rf /var/lib/apt/lists/*
fi
PYTHON=python3
echo ">>> python: $($PYTHON -V) ($(command -v $PYTHON))"
if [[ -n "${PYTHON_MIN:-}" ]] && ! $PYTHON -c \
  "import sys; sys.exit(0 if sys.version_info[:2] >= tuple(int(x) for x in '${PYTHON_MIN}'.split('.')) else 1)"; then
  echo "ERROR: python в образе $($PYTHON -V) старее requires-python проекта (>=${PYTHON_MIN});" \
       "wheel-ы получились бы для чужого ABI. Возьмите образ с python ${PYTHON_MIN}+." >&2
  exit 1
fi

$PYTHON -m venv /opt/venv
export PATH="/opt/venv/bin:$PATH"
export UV_PROJECT_ENVIRONMENT=/opt/venv
export UV_LINK_MODE=copy
pip install --no-cache-dir -U pip uv

WHEELS=/wheels
PYTORCH_INDEX="${PYTORCH_INDEX}"
PYPI_INDEX="${PYPI_INDEX}"
TORCH_VERSION="${TORCH_VERSION}"
USE_UV="${USE_UV_EXPORT}"
UV_PROJECT_DIR="${UV_PROJECT_DIR:-.}"
# Кэш uv — только внутри контейнера (bind-mount Windows ломает atomic rename в .uv-cache)
UV_CACHE_DIR="/tmp/uv-cache"
export UV_CACHE_DIR
mkdir -p "$UV_CACHE_DIR"

echo "mount-check-$(date +%s)" > "${WHEELS}/.mount-check"
if [[ ! -f "${WHEELS}/.mount-check" ]]; then
  echo "ERROR: /wheels недоступен - проверьте Docker mount path" >&2
  exit 1
fi

harvest_uv_wheels() {
  # Остаточный сбор из /tmp (если где-то вызывался uv pip)
  find "$UV_CACHE_DIR" -type f -name "*.whl" -exec cp -un {} "$WHEELS"/ \; 2>/dev/null || true
}

# PIP_INDEX_ARGS: space-separated --index-url/--extra-index-url from resolver
# shellcheck disable=SC2206
pip_index_args=( ${PIP_INDEX_ARGS} )

# Allow HTTP corporate indexes (Nexus without TLS)
for ((i=0; i<${#pip_index_args[@]}; i++)); do
  arg="${pip_index_args[$i]}"
  if [[ "$arg" == --index-url || "$arg" == --extra-index-url ]]; then
    url="${pip_index_args[$((i+1))]:-}"
    case "$url" in
      http://*|https://*)
        host="$(echo "$url" | sed -E 's#^https?://([^/:]+).*#\1#')"
        pip_index_args+=(--trusted-host "$host")
        ;;
    esac
  fi
done

pip_common=(
  --dest "$WHEELS"
  --prefer-binary
  --ignore-requires-python
  --retries 5
  --timeout 60
  --find-links "$WHEELS"
  "${pip_index_args[@]}"
)

# Index-only (без find-links) — recovery, когда в /wheels лежит чужая версия пакета
pip_index_only=(
  --dest "$WHEELS"
  --prefer-binary
  --ignore-requires-python
  --retries 5
  --timeout 60
  "${pip_index_args[@]}"
)

download_req_file() {
  # $1=requirements path; $2=optional "no-deps"
  local req="$1"
  local no_deps="${2:-}"
  local extra=( )
  local deps_flag=( )
  if [[ "$no_deps" == "no-deps" ]]; then
    deps_flag=( --no-deps )
  fi
  if [[ -n "$TORCH_VERSION" && -f /tmp/constraints.txt ]]; then
    extra=( -c /tmp/constraints.txt )
  fi
  if [[ -f /opt/prune_stale_wheels.py ]]; then
    echo ">>> prune stale wheels vs ${req}"
    python3 /opt/prune_stale_wheels.py "$req" "$WHEELS" || true
  fi
  if pip download "${pip_common[@]}" "${deps_flag[@]}" "${extra[@]}" -r "$req"; then
    return 0
  fi
  echo "WARN: pip download -r failed; retry via index (без find-links)" >&2
  if [[ -f /opt/prune_stale_wheels.py ]]; then
    python3 /opt/prune_stale_wheels.py "$req" "$WHEELS" || true
  fi
  # Повтор без find-links — убирает «from versions: только локальная»
  pip download "${pip_index_only[@]}" "${deps_flag[@]}" "${extra[@]}" -r "$req"
}

echo ""
echo ">>> [1/4] pip, uv, setuptools, wheel"
pip download "${pip_common[@]}" pip uv setuptools wheel

if [[ -n "$TORCH_VERSION" ]]; then
  echo ""
  echo ">>> [2/4] torch + nvidia-* (base image)"
  if compgen -G "${WHEELS}/torch-${TORCH_VERSION}+cu128*.whl" > /dev/null \
     && compgen -G "${WHEELS}/nvidia_cublas_cu12*.whl" > /dev/null; then
    echo "    torch cu128 и nvidia-* уже в wheels/, пропуск"
  else
    pip download "${pip_common[@]}" "torch==${TORCH_VERSION}"
  fi

  echo ""
  echo ">>> [2b] torchaudio==${TORCH_VERSION}"
  pip download "${pip_common[@]}" "torchaudio==${TORCH_VERSION}"
fi

IFS="|" read -ra _extra_specs <<< "${EXTRA_WHEEL_SPECS}"
for spec in "${_extra_specs[@]}"; do
  [[ -z "$spec" ]] && continue
  echo ""
  echo ">>> [2c] extra wheel: ${spec}"
  pip download "${pip_common[@]}" "$spec"
done

if [[ "$USE_UV" == "1" ]]; then
  echo ""
  echo ">>> [3/4] uv export deps (prune: ${UV_EXPORT_PRUNE})"
  cd "/app/${UV_PROJECT_DIR}"
  prune_args=()
  for pkg in ${UV_EXPORT_PRUNE}; do
    prune_args+=(--prune "$pkg")
  done
  uv export --frozen --no-dev --no-emit-project \
    "${prune_args[@]}" \
    --no-hashes \
    -o /tmp/app-requirements.txt
  # --no-deps: uv export уже полный + учитывает override-dependencies
  # (напр. ctranslate2>=4.5 при whisperx, который пинит <4.5). pip иначе
  # падает с ResolutionImpossible.
  if [[ -n "$TORCH_VERSION" ]]; then
    printf 'torch==%s\ntorchaudio==%s\n' "$TORCH_VERSION" "$TORCH_VERSION" > /tmp/constraints.txt
  fi
  download_req_file /tmp/app-requirements.txt no-deps
  rm -f /wheels/torch-2.1[0-9].0-*.whl /wheels/torch-2.13*.whl \
        /wheels/torchaudio-2.1[0-9]* /wheels/torchaudio-2.2* 2>/dev/null || true
elif [[ -f /app/requirements.txt ]]; then
  echo ""
  echo ">>> [3/4] requirements.txt (без uv.lock)"
  cp /app/requirements.txt /tmp/app-requirements.txt
  download_req_file /tmp/app-requirements.txt
fi

echo ""
echo ">>> [3b] cython/setuptools + av fallback"
pip download "${pip_common[@]}" "cython>=3.1.0a1,<4" "setuptools>=77" || true
if ! compgen -G "/wheels/av-14.4.0-*.whl" > /dev/null; then
  pip download "${pip_common[@]}" --only-binary=:all: "av==14.2.0" || true
  pip wheel --no-deps --wheel-dir /wheels "av==14.4.0" \
    || echo "    WARN: av 14.4.0 build failed"
fi
rm -f /wheels/av-*.tar.gz 2>/dev/null || true

echo ""
echo ">>> [3c] wheel из sdist (docopt, julius, antlr4)"
pip install --no-cache-dir wheel
for pkg in docopt julius antlr4-python3-runtime; do
  if compgen -G "/wheels/${pkg}-*.whl" > /dev/null; then
    continue
  fi
  if compgen -G "/wheels/${pkg}-*.tar.gz" > /dev/null; then
    pip wheel --no-deps --wheel-dir /wheels /wheels/${pkg}-*.tar.gz \
      && rm -f /wheels/${pkg}-*.tar.gz
  fi
done

echo ""
echo ">>> [4/4] ctranslate2>=4.5.0"
pip download "${pip_common[@]}" "ctranslate2>=4.5.0" || true

harvest_uv_wheels

count="$(find "$WHEELS" -maxdepth 1 -name "*.whl" | wc -l)"
nvidia_count="$(find "$WHEELS" -maxdepth 1 -name "nvidia_*.whl" | wc -l)"
echo ""
echo "=== Готово: ${count} wheel-файлов (${nvidia_count} nvidia_*) в ${WHEELS} ==="
du -sh "$WHEELS"
"""


def download_wheels(ctx: ProjectContext) -> None:
    if not ctx.config.python_lock_paths() and not (ctx.root / "requirements.txt").is_file():
        print("=== download-wheels: SKIP (нет pyproject.toml/uv.lock/requirements.txt) ===")
        return

    ctx.ensure_offline_dirs()
    try:
        current = ctx.python_deps_hash()
    except RuntimeError:
        current = "no-lock-files"

    whl_count = len(list(ctx.wheels_dir.glob("*.whl")))
    mount_check = ctx.wheels_dir / ".mount-check"
    critical_ok = all(
        any(ctx.wheels_dir.glob(wp.pattern)) for wp in ctx.config.critical_wheels
    )
    if (
        ctx.wheels_hash_file.is_file()
        and ctx.wheels_hash_file.read_text(encoding="utf-8").strip() == current
        and mount_check.is_file()
        and whl_count >= 10
        and critical_ok
    ):
        print(
            f"=== download-wheels: lockfile не менялся, cache актуален ({whl_count} .whl) ==="
        )
        print(docker_cmd.dir_size_human(ctx.wheels_dir))
        return

    tv = ctx.config.torch_version() or ""
    pytorch_index = os.environ.get("PYTORCH_INDEX", ctx.config.pytorch_index)
    pypi_index = os.environ.get("PYPI_INDEX", ctx.config.pypi_index)
    resolver = ctx.config.package_resolver()
    from offline_docker.resolve import pip_index_chain_for_download

    chain, used_fallback = pip_index_chain_for_download(
        resolver,
        pypi_index=pypi_index,
        pytorch_index=pytorch_index,
    )
    pip_index_args: list[str] = []
    if chain:
        pip_index_args.extend(["--index-url", chain[0]])
        for url in chain[1:]:
            pip_index_args.extend(["--extra-index-url", url])
    pip_index_args_str = " ".join(pip_index_args)

    root_docker = docker_mount_path(ctx.root)
    wheels_docker = docker_mount_path(ctx.wheels_dir)
    import offline_docker.wheel_prune as wheel_prune

    prune_host = Path(wheel_prune.__file__).resolve()
    prune_docker = docker_mount_path(prune_host)

    print("=== download-wheels ===")
    print(f"Корень:           {ctx.root}")
    print(f"Offline cache:    {ctx.offline_cache}")
    print(f"Каталог wheels:   {ctx.wheels_dir}")
    print(f"torch:            {tv or '(нет)'}")
    print(f"use_uv_export:    {ctx.config.use_uv_export}")
    print(f"python project:   {ctx.config.effective_python_project_dir()}")
    print(
        "Python (образ):   "
        f"{ctx.config.deb_ubuntu_image} (нужно >= {ctx.config.python_requires_min() or '—'})"
    )
    print(f"Resolve:          {' -> '.join(resolver.settings.resolve.order)}")
    print(f"PyPI chain:       {' -> '.join(chain) if chain else '(find-links only)'}")
    if used_fallback and resolver.is_local_only():
        print()
        print(
            "WARN: sources.json = local-only; для download временно добавлен "
            "PyPI/PyTorch index."
        )
        print(
            "      Для явного режима заполнения кэша: "
            "offdock configure --with-upstream"
        )
    print()

    from offline_docker.sync_cache import maybe_materialize

    maybe_materialize(ctx)

    prune = " ".join(ctx.config.uv_export_prune)
    extra = "|".join(ctx.config.extra_wheel_specs)
    project_dir = ctx.config.effective_python_project_dir()

    env = [
        f"TORCH_VERSION={tv}",
        f"PYTORCH_INDEX={pytorch_index}",
        f"PYPI_INDEX={chain[0] if chain else pypi_index}",
        f"PIP_INDEX_ARGS={pip_index_args_str}",
        f"USE_UV_EXPORT={'1' if ctx.config.use_uv_export else '0'}",
        f"UV_PROJECT_DIR={project_dir}",
        f"UV_EXPORT_PRUNE={prune}",
        f"EXTRA_WHEEL_SPECS={extra}",
        f"PYTHON_MIN={ctx.config.python_requires_min() or ''}",
    ]

    docker_cmd.run(
        [
            "docker",
            "run",
            "--rm",
            *[item for pair in env for item in ("-e", pair)],
            "-v",
            f"{root_docker}:/app:ro",
            "-v",
            f"{wheels_docker}:/wheels",
            "-v",
            f"{prune_docker}:/opt/prune_stale_wheels.py:ro",
            ctx.config.deb_ubuntu_image,
            "bash",
            "-ec",
            WHEELS_GUEST_UV,
        ],
        env={"DOCKER_BUILDKIT": "0"},
    )

    if not mount_check.is_file():
        raise SystemExit(
            "ERROR: wheels не попали на хост - проверьте Docker mount path (D:/..., не /d/...)"
        )

    ctx.wheels_hash_file.write_text(current + "\n", encoding="utf-8")
    print()
    nvidia = sorted(ctx.wheels_dir.glob("nvidia_*.whl"))
    if nvidia:
        print("NVIDIA-пакеты на хосте:")
        for p in nvidia:
            print(p.name)

    if resolver.settings.resolve.fill_local:
        from offline_docker.sync_cache import publish_to_remotes

        publish_to_remotes(ctx)
