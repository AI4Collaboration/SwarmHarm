#!/bin/bash
# 在本机运行：在每台 runtime 上用任务的参考解法验证任务环境和性能（runtime-task-check.sh），随后确认 runtime 上没有留下解法文件。参数：EXP
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; D=$(exp_dir "$EXP"); N=$(exp_field "$EXP" n_agents); TASK=$(exp_field "$EXP" task)
fetch_shared_key
SSH=$(exp_ssh "$EXP")
for i in $(seq 1 "$N"); do
  L=$(letter "$i"); H=$(host_field "$EXP" "rt-$L" public)
  echo "######## rt-$L ($TASK)"
  $SSH ubuntu@$H 'sudo rm -rf /tmp/swh30-check && mkdir -p /tmp/swh30-check'
  scp -q -r -i "$SHARED_KEY" -o StrictHostKeyChecking=accept-new "$BUNDLE_DIR/tasks/$TASK/solution" ubuntu@$H:/tmp/swh30-check/
  $SSH ubuntu@$H "sudo bash -s $TASK" < "$BUNDLE_DIR/provision/runtime-task-check.sh" 2>&1 | tee "$D/logs/task-check-rt-$L.txt" | tail -n 30
  # solve.sh / 解法文件在检查结束后必须全部消失
  $SSH ubuntu@$H 'sudo find / -xdev \( -name solve.sh -o -name swh30-check -o -name chk-task -o -name chk-app \) -not -path "/proc/*" 2>/dev/null | grep -v "^/usr/\|^/opt/elan/\|^/home/agent/.elan" || echo "no solution files left"'
done
