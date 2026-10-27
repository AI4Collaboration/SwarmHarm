# Source from the repository root on an Alliance Canada cluster (login or compute node).
# Selects the pinned Harbor runtime and the Apptainer workstation backend.
SWARMHARM_ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
SWARMHARM_READINESS=${SWARMHARM_READINESS:-"$SWARMHARM_ROOT/../eval-readiness"}
module load apptainer/1.4.5 >/dev/null 2>&1 || { echo 'apptainer module unavailable' >&2; return 1; }
# Site defaults bind /project, /scratch and home into every container.
unset APPTAINER_BIND SINGULARITY_BIND
export SWARMHARM_SANDBOX=apptainer
export SWARMHARM_SIF=${SWARMHARM_SIF:-"$SWARMHARM_READINESS/images/python-3.12-slim.sif"}
export PY="$SWARMHARM_READINESS/harbor-0.24.0/bin/python"
for required in "$PY" "$SWARMHARM_SIF"; do
  [ -e "$required" ] || { echo "Missing $required; run scripts/alliance/setup.sh" >&2; return 1; }
done
