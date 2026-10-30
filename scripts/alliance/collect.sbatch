#!/bin/bash
# Collect one prepared registration inside a Slurm job.
# sbatch --account=<def-...> scripts/alliance/collect.sbatch <output-dir> <registration-dir> <key-file>
#SBATCH --job-name=swarmharm-collect
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --output=%x-%j.out
set -euo pipefail
OUT=$1; REG=$2; KEY=$3
cd "${SLURM_SUBMIT_DIR:?}"
source scripts/alliance/env.sh
PID=$("$PY" experiments/swarmharm-v1/launch.py --output "$OUT" --registration-dir "$REG" --key-file "$KEY" \
  | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["pid"])')
echo "collector pid $PID on $(hostname), job $SLURM_JOB_ID"
# launch.py detaches the collector; Slurm ends every job process when this script exits.
while kill -0 "$PID" 2>/dev/null; do sleep 30; done
echo "collector exited; completion.json present: $([ -f "$OUT/completion.json" ] && echo yes || echo no)"
