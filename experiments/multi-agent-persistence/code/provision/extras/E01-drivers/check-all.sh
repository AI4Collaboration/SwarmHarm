#!/bin/bash
# RUNBOOK 第 5/6 节检查 1 与 5：在每个 runtime 上并行运行 runtime-check.sh，输出写入 .scratch/<EXP>/checks/<LABEL>-rt-<x>.log。
# 参数：EXP LABEL（phase1 | phase2）。phase1 额外执行检查 4（任务环境 + gold/test patch 的一次性 worktree）。
set -uo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; LABEL=$2
N=$(exp_field "$EXP" n_agents); TASK=$(exp_field "$EXP" task); HARNESS=$(exp_field "$EXP" harness)
D=$(exp_dir "$EXP"); mkdir -p "$D/checks"
EIP=$(host_field "$EXP" multica public); PP=$(host_field "$EXP" proxy private)
SSH=$(exp_ssh "$EXP")
one() {
  local L=$1 H
  H=$(host_field "$EXP" "rt-$L" public)
  $SSH ubuntu@"$H" "sudo -u agent -H bash -s $PP $EIP $HARNESS" < "$BUNDLE_DIR/provision/runtime-check.sh"
}
pids=()
for i in $(seq 1 "$N"); do
  L=$(letter "$i")
  one "$L" > "$D/checks/$LABEL-rt-$L.log" 2>&1 &
  pids+=($!)
done
for p in "${pids[@]}"; do wait "$p"; done
for i in $(seq 1 "$N"); do L=$(letter "$i"); echo "===== $LABEL rt-$L"; cat "$D/checks/$LABEL-rt-$L.log"; done
