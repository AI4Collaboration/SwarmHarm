#!/bin/bash
# One-time setup on an Alliance Canada login node (needs internet).
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
READINESS=${SWARMHARM_READINESS:-"$ROOT/../eval-readiness"}
UV_VERSION=0.13.0
mkdir -p "$READINESS/images" "$READINESS/tools"
module load apptainer/1.4.5

# Alliance Python modules reject manylinux wheels, so Harbor's dependencies
# (litellm, pydantic-core, ...) would compile from source. Use uv's standalone
# CPython instead, outside the Alliance wheelhouse.
UV="$READINESS/tools/uv-$UV_VERSION/uv"
if [ ! -x "$UV" ]; then
  mkdir -p "$(dirname "$UV")"
  curl -fsSL "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-x86_64-unknown-linux-gnu.tar.gz" \
    | tar -xz -C "$(dirname "$UV")" --strip-components=1
fi
export UV_PYTHON_INSTALL_DIR="$READINESS/tools/python" UV_CACHE_DIR="${SCRATCH:-$READINESS}/.uv-cache"
export PIP_CONFIG_FILE=/dev/null
unset PYTHONPATH
if [ ! -x "$READINESS/harbor-0.24.0/bin/python" ]; then
  "$UV" venv --python 3.12 --managed-python --seed "$READINESS/harbor-0.24.0"
fi
"$UV" pip install --python "$READINESS/harbor-0.24.0/bin/python" "harbor==0.24.0"
"$UV" pip freeze --python "$READINESS/harbor-0.24.0/bin/python" > "$READINESS/harbor-0.24.0/dependencies.txt"

SIF="$READINESS/images/python-3.12-slim.sif"
if [ ! -f "$SIF" ]; then
  # Same image family as the Docker host, rebuilt for x86_64.
  APPTAINER_CACHEDIR=${APPTAINER_CACHEDIR:-"${SCRATCH:-$READINESS}/.apptainer-cache"} \
    apptainer pull "$SIF" docker://python:3.12-slim
  sha256sum "$SIF" > "$SIF.sha256"
fi
# Pinned Pi agent harness and pi-goal extension, installed from the lockfile.
NODE_DIR=/cvmfs/soft.computecanada.ca/easybuild/software/2023/x86-64-v4/Compiler/gcccore/nodejs/24.22.1/bin
(cd "$ROOT/experiments/runtime/pi" && PATH="$NODE_DIR:$PATH" npm ci --ignore-scripts --no-fund --no-audit)
echo "Node: $("$NODE_DIR/node" --version)"
echo "Harbor: $("$READINESS/harbor-0.24.0/bin/python" -c 'from importlib.metadata import version; print(version("harbor"))')"
echo "SIF: $(cat "$SIF.sha256")"
