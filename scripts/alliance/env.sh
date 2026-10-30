# Source from the repository root on an Alliance Canada cluster (login or compute node).
# Selects the pinned Harbor runtime and the Apptainer workstation backend.
SWARMHARM_ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
SWARMHARM_READINESS=${SWARMHARM_READINESS:-"$SWARMHARM_ROOT/../eval-readiness"}
module load apptainer/1.4.5 >/dev/null 2>&1 || { echo 'apptainer module unavailable' >&2; return 1; }
# Site defaults bind /project, /scratch and home into every container.
unset APPTAINER_BIND SINGULARITY_BIND
export SWARMHARM_SANDBOX=apptainer
export SWARMHARM_SIF=${SWARMHARM_SIF:-"$SWARMHARM_READINESS/images/python-3.12-slim.sif"}
export SWARMHARM_HARBOR_ENV=${SWARMHARM_HARBOR_ENV:-"$SWARMHARM_READINESS/harbor-0.24.0"}
export PY="$SWARMHARM_HARBOR_ENV/bin/python"
# The Pi agent harness needs Node.js >= 22.19.
module load StdEnv/2023 nodejs/24.22.1 >/dev/null 2>&1 || true
NODE_DIR=/cvmfs/soft.computecanada.ca/easybuild/software/2023/x86-64-v4/Compiler/gcccore/nodejs/24.22.1/bin
case ":$PATH:" in *":$NODE_DIR:"*) ;; *) export PATH="$NODE_DIR:$PATH" ;; esac
export SWARMHARM_NODE="$NODE_DIR/node"
for required in "$PY" "$SWARMHARM_SIF" "$SWARMHARM_NODE" "$SWARMHARM_ROOT/experiments/runtime/pi/node_modules"; do
  [ -e "$required" ] || { echo "Missing $required; run scripts/alliance/setup.sh" >&2; return 1; }
done
