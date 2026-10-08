#!/bin/bash
# 在本机运行：对每台 runtime 运行 runtime-check.sh（harness 经 AxonHub 使用 shell 工具、免密 sudo、SSH 互登、代理白名单、直连被拒）。参数：EXP
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; D=$(exp_dir "$EXP"); N=$(exp_field "$EXP" n_agents); HARNESS=$(exp_field "$EXP" harness)
fetch_shared_key
SSH=$(exp_ssh "$EXP")
EIP=$(host_field "$EXP" multica public); PP=$(host_field "$EXP" proxy private)
for i in $(seq 1 "$N"); do
  L=$(letter "$i"); H=$(host_field "$EXP" "rt-$L" public)
  PEERS=(); for j in $(seq 1 "$N"); do [ "$j" = "$i" ] || PEERS+=("dev-$(letter "$j")"); done
  echo "######## rt-$L"
  $SSH ubuntu@$H "sudo -u agent -H bash -s $PP $EIP $HARNESS ${PEERS[*]}" < "$BUNDLE_DIR/provision/runtime-check.sh" 2>&1 | tee "$D/logs/check-rt-$L-$(date -u +%H%M%S).txt"
done
