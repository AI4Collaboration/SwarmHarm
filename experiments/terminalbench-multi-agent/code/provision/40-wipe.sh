#!/bin/bash
# 在本机运行：验证结束后清空 runtime 的历史与 Multica workspace 中的全部 issue，使实验从干净状态开始。参数：EXP
# runtime-clear-history.sh 保留 ~/.multica/daemon.id，agent 与 runtime 的绑定保持有效。
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; D=$(exp_dir "$EXP"); N=$(exp_field "$EXP" n_agents)
fetch_shared_key
SSH=$(exp_ssh "$EXP")
for i in $(seq 1 "$N"); do
  H=$(host_field "$EXP" "rt-$(letter "$i")" public)
  $SSH ubuntu@$H 'sudo bash -s' < "$BUNDLE_DIR/provision/runtime-clear-history.sh" > "$D/logs/clear-rt-$(letter "$i").log" 2>&1
  $SSH ubuntu@$H 'sudo systemctl start multica-runtime && sleep 5 && systemctl is-active multica-runtime'
done
M="$BUNDLE_DIR/provision/m30.sh"; A="$BUNDLE_DIR/provision/api30.sh"
for _ in 1 2 3; do
  IDS=$("$M" "$EXP" issue list --limit 100 --output json | jq -r '(.issues // .)[]?.id')
  [ -n "$IDS" ] || break
  for id in $IDS; do "$A" "$EXP" DELETE "/api/issues/$id" >/dev/null; done
done
echo "issues left: $("$M" "$EXP" issue list --limit 100 --output json | jq '(.issues // .) | length')"
