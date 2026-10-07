#!/bin/bash
# 配置一台 runtime（RUNBOOK 第 4 节）。参数：EXP LETTER。网络仍然开放时运行
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; L=$2
D=$(exp_dir "$EXP")
TASK=$(exp_field "$EXP" task); HARNESS=$(exp_field "$EXP" harness); MODEL=$(exp_field "$EXP" model)
PP=$(host_field "$EXP" proxy private); H=$(host_field "$EXP" rt-$L public); EIP=$(host_field "$EXP" multica public)
SSH="$(exp_ssh "$EXP") ubuntu@$H"
PAT=$(jq -r .pat "$D/multica-account.json"); WS=$(jq -r .workspace.id "$D/multica-account.json")
KEY=$(jq -r ".\"swh13-$EXP-rt-$L\"" "$D/axonhub-keys.json")
$SSH "sudo bash -s $PP" < "$BUNDLE_DIR/provision/runtime-base.sh"
$SSH 'sudo mkdir -p /opt/swh13/task && sudo chmod 755 /opt/swh13 /opt/swh13/task'
scp -q -i "$D/swh13-$EXP-ed25519" -o StrictHostKeyChecking=accept-new "$BUNDLE_DIR/tasks/$TASK/env.json" "$BUNDLE_DIR/tasks/$TASK/requirements.lock" ubuntu@$H:/tmp/
$SSH 'sudo mv /tmp/env.json /tmp/requirements.lock /opt/swh13/task/ && sudo chmod 644 /opt/swh13/task/*'
$SSH "sudo bash -s $TASK" < "$BUNDLE_DIR/provision/task-env.sh"
$SSH "sudo bash -s swh13-$EXP-rt-$L $PP https://$EIP $PAT $WS $KEY $HARNESS $MODEL" < "$BUNDLE_DIR/provision/runtime-config.sh"
echo "runtime $L done"
