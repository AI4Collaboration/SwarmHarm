#!/usr/bin/env bash
# Prepare E1 registrations in parallel, one per RUN_ID, sharing one filing deadline.
# Usage: e1_prepare.sh DEADLINE_UTC RUN_ID...   (RUN_ID like 2026-10-27-e1-sol-r01)
# The model comes from the RUN_ID (-glm- or -sol-). Outputs go to
# ../eval-readiness/swarmharm-v1-RUN_ID, logs to ../eval-readiness/logs.
# OPENROUTER_KEY_FILE overrides the host-only key path.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=../eval-readiness/harbor-0.24.0/bin/python
KEY=${OPENROUTER_KEY_FILE:-$HOME/swarm-harm/keys/openrouter.key}
DEADLINE=$1; shift
mkdir -p ../eval-readiness/logs
for RUN in "$@"; do
  case "$RUN" in
    *-glm-*) MODEL=(--model-id z-ai/glm-5.3 --model-alias glm
                    --openrouter-provider-routing '{"quantizations": ["bf16", "fp8"]}') ;;
    *-sol-*) MODEL=(--model-id openai/gpt-5.6-sol --model-alias sol) ;;
    *) echo "unknown model in $RUN" >&2; exit 2 ;;
  esac
  [ -e "../eval-readiness/swarmharm-v1-$RUN" ] && { echo "output exists: $RUN" >&2; exit 2; }
  "$PY" experiments/swarmharm-v1/run.py --phase prepare --scenario engineering-maintenance \
    --output "../eval-readiness/swarmharm-v1-$RUN" \
    --registration-dir "experiments/swarmharm-v1/registrations/$RUN" \
    --key-file "$KEY" --provider openrouter "${MODEL[@]}" \
    --population 4 --active-contexts 4 --provider-concurrency 4 \
    --filing-deadline-utc "$DEADLINE" --cue-condition agent_initiated_activity \
    > "../eval-readiness/logs/prepare-$RUN.log" 2>&1 &
done
FAILED=0
for job in $(jobs -p); do wait "$job" || FAILED=$((FAILED + 1)); done
for RUN in "$@"; do
  printf '%s ' "$RUN"; tail -n 1 "../eval-readiness/logs/prepare-$RUN.log" | cut -c1-60
done
exit "$FAILED"
