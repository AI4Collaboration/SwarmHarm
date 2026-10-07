#!/bin/bash
# RUNBOOK 第 6 节末尾：等所有验证 run 结束，清除每台 runtime 的历史并重启 daemon，删除工作区内全部 issue。参数：EXP
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1
N=$(exp_field "$EXP" n_agents)
M="$BUNDLE_DIR/provision/m13.sh"
SSH=$(exp_ssh "$EXP")
IDS=$("$M" "$EXP" issue list --limit 100 --output json | jq -r '(.issues // .)[].id')
for _ in $(seq 1 60); do
  ACTIVE=0
  for id in $IDS; do
    A=$("$M" "$EXP" issue runs "$id" --active --output json | jq 'if type=="array" then length else (.runs // [] | length) end')
    ACTIVE=$((ACTIVE + A))
  done
  echo "active runs: $ACTIVE"
  [ "$ACTIVE" -eq 0 ] && break
  sleep 10
done
[ "$ACTIVE" -eq 0 ]
for i in $(seq 1 "$N"); do
  L=$(letter "$i"); H=$(host_field "$EXP" rt-$L public)
  echo "##### rt-$L"
  $SSH ubuntu@$H 'sudo bash -s' < "$(dirname "$0")/runtime-clear-history.sh" | tail -n 4
  $SSH ubuntu@$H 'sudo systemctl start multica-runtime; sleep 5; systemctl is-active multica-runtime'
done
for id in $IDS; do "$BUNDLE_DIR/provision/api13.sh" "$EXP" DELETE "/api/issues/$id" >/dev/null; done
echo "issues left: $("$M" "$EXP" issue list --limit 100 --output json | jq '(.issues // .) | length')"
"$M" "$EXP" runtime list --output json | jq -r '.[] | "\(.name)\t\(.status)"'
