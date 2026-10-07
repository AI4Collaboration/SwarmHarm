#!/bin/bash
# 在所有 runtime 上并行运行 runtime-check.sh（harness 工具调用、sudo、代理、直连出口），日志写入 .scratch/<EXP>/logs/check-<PHASE>-<L>.log。
# 参数：EXP PHASE（如 phase1、phase2）。任务环境检查（RUNBOOK 第 5 节第 4 项）另见 task-check.sh。
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; PHASE=$2
N=$(exp_field "$EXP" n_agents); HARNESS=$(exp_field "$EXP" harness)
PP=$(host_field "$EXP" proxy private); EIP=$(host_field "$EXP" multica public)
SSH=$(exp_ssh "$EXP")
PIDS=()
for i in $(seq 1 "$N"); do
  L=$(letter "$i"); H=$(host_field "$EXP" rt-$L public)
  $SSH ubuntu@$H "sudo -u agent -H bash -s $PP $EIP $HARNESS" < "$(dirname "$0")/runtime-check.sh" > "$(exp_dir "$EXP")/logs/check-$PHASE-$L.log" 2>&1 &
  PIDS+=($!)
done
for p in "${PIDS[@]}"; do wait "$p" || true; done
for i in $(seq 1 "$N"); do L=$(letter "$i"); echo "##### rt-$L"; cat "$(exp_dir "$EXP")/logs/check-$PHASE-$L.log"; done
