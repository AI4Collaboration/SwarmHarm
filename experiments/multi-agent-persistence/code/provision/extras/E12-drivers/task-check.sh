#!/bin/bash
# 任务环境检查（RUNBOOK 第 5 节第 4 项）：把 gold.patch 与 test.patch 临时放到一台 runtime，在一次性 worktree 中运行 F2P 测试文件，随后清理并验证两个补丁不再存在。
# 参数：EXP LETTER TEST_FILE
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; L=$2; TEST_FILE=$3
TASK=$(exp_field "$EXP" task); H=$(host_field "$EXP" rt-$L public)
SSH=$(exp_ssh "$EXP")
SCP="scp -q -i $(exp_dir "$EXP")/swh13-$EXP-ed25519 -o StrictHostKeyChecking=accept-new"
$SSH ubuntu@$H 'sudo mkdir -p /tmp/swh13-check && sudo chmod 777 /tmp/swh13-check'
$SCP "$BUNDLE_DIR/tasks/$TASK/gold.patch" "$BUNDLE_DIR/tasks/$TASK/test.patch" ubuntu@$H:/tmp/swh13-check/
$SSH ubuntu@$H "sudo bash -s $TEST_FILE" < "$(dirname "$0")/runtime-task-check.sh"
echo "== patches left on runtime:"
$SSH ubuntu@$H 'sudo find / -xdev \( -name gold.patch -o -name test.patch \) 2>/dev/null; echo "(find done)"; ls -d /tmp/swh13-check 2>&1 | head -n 1'
echo "== documented test command as agent"
$SSH ubuntu@$H "sudo -u agent -H bash -c 'source ~/work/qutebrowser/.venv/bin/activate && cd ~/work/qutebrowser && python -m pytest -q $TEST_FILE 2>&1 | tail -n 3'"
