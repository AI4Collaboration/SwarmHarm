#!/usr/bin/env bash
# Start one detached collector per frozen, committed and pushed E1 registration.
# Usage: e1_launch.sh RUN_ID...   OPENROUTER_KEY_FILE overrides the key path.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=../eval-readiness/harbor-0.24.0/bin/python
KEY=${OPENROUTER_KEY_FILE:-$HOME/swarm-harm/keys/openrouter.key}
mkdir -p ../eval-readiness/logs
for RUN in "$@"; do
  setsid nohup "$PY" experiments/swarmharm-v1/launch.py \
    --output "../eval-readiness/swarmharm-v1-$RUN" \
    --registration-dir "experiments/swarmharm-v1/registrations/$RUN" \
    --key-file "$KEY" > "../eval-readiness/logs/collect-$RUN.log" 2>&1 < /dev/null &
done
