#!/bin/bash
# 在操作机上依次完成一台 runtime 的基础环境、任务环境、harness 配置与 daemon。参数：EXP LETTER
# 各 runtime 之间互不依赖，可对不同 LETTER 并行调用；日志写入 .scratch/<EXP>/logs/runtime-<LETTER>.log
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; L=$2
D=$(exp_dir "$EXP")
TASK=$(exp_field "$EXP" task); HARNESS=$(exp_field "$EXP" harness); MODEL=$(exp_field "$EXP" model)
PP=$(host_field "$EXP" proxy private); H=$(host_field "$EXP" rt-$L public); EIP=$(host_field "$EXP" multica public)
PAT=$(jq -r .pat "$D/multica-account.json"); WS=$(jq -r .workspace.id "$D/multica-account.json")
KEY=$(jq -r ".\"swh13-$EXP-rt-$L\"" "$D/axonhub-keys.json")
SSH=$(exp_ssh "$EXP")
SCP="scp -q -i $D/swh13-$EXP-ed25519 -o StrictHostKeyChecking=accept-new"
$SSH ubuntu@$H "sudo bash -s $PP" < "$(dirname "$0")/runtime-base.sh"
$SSH ubuntu@$H 'sudo mkdir -p /opt/swh13/task && sudo chmod 755 /opt/swh13 /opt/swh13/task'
$SCP "$BUNDLE_DIR/tasks/$TASK/env.json" "$BUNDLE_DIR/tasks/$TASK/requirements.lock" ubuntu@$H:/home/ubuntu/
$SSH ubuntu@$H 'sudo mv /home/ubuntu/env.json /home/ubuntu/requirements.lock /opt/swh13/task/ && sudo chmod 644 /opt/swh13/task/*'
$SSH ubuntu@$H "sudo bash -s $TASK" < "$(dirname "$0")/task-env.sh"
$SSH ubuntu@$H "sudo bash -s swh13-$EXP-rt-$L $PP https://$EIP $PAT $WS $KEY $HARNESS $MODEL" < "$(dirname "$0")/runtime-config.sh"
echo "runtime $L done"
