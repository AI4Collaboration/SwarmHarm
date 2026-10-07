#!/bin/bash
# RUNBOOK 第 4 节：并行配置全部 runtime。参数：EXP。前置：multica 账号、proxy 已就绪；AxonHub keys 在 .scratch/<EXP>/axonhub-keys.json
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1
N=$(exp_field "$EXP" n_agents); TASK=$(exp_field "$EXP" task); HARNESS=$(exp_field "$EXP" harness); MODEL=$(exp_field "$EXP" model)
D=$(exp_dir "$EXP")
EIP=$(host_field "$EXP" multica public); PP=$(host_field "$EXP" proxy private)
PAT=$(jq -r .pat "$D/multica-account.json"); WS=$(jq -r .workspace.id "$D/multica-account.json")
SSH=$(exp_ssh "$EXP")
setup_one() {
  local i=$1 L H KEY
  L=$(letter "$i"); H=$(host_field "$EXP" "rt-$L" public)
  KEY=$(jq -r ".\"swh13-$EXP-rt-$L\"" "$D/axonhub-keys.json")
  $SSH ubuntu@"$H" "sudo bash -s $PP" < "$BUNDLE_DIR/provision/runtime-base.sh"
  $SSH ubuntu@"$H" 'sudo mkdir -p /opt/swh13/task && sudo chmod 755 /opt/swh13 /opt/swh13/task'
  scp -i "$D/swh13-$EXP-ed25519" -o StrictHostKeyChecking=accept-new "$BUNDLE_DIR/tasks/$TASK/env.json" "$BUNDLE_DIR/tasks/$TASK/requirements.lock" ubuntu@"$H":/tmp/
  $SSH ubuntu@"$H" 'sudo mv /tmp/env.json /tmp/requirements.lock /opt/swh13/task/ && sudo chmod 644 /opt/swh13/task/*'
  $SSH ubuntu@"$H" "sudo bash -s $TASK" < "$BUNDLE_DIR/provision/task-env.sh"
  $SSH ubuntu@"$H" "sudo bash -s swh13-$EXP-rt-$L $PP https://$EIP $PAT $WS $KEY $HARNESS $MODEL" < "$BUNDLE_DIR/provision/runtime-config.sh"
}
pids=()
for i in $(seq 1 "$N"); do
  setup_one "$i" > "$D/logs/setup-rt-$(letter "$i").log" 2>&1 &
  pids+=($!)
done
rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done
for i in $(seq 1 "$N"); do echo "== rt-$(letter "$i")"; tail -n 12 "$D/logs/setup-rt-$(letter "$i").log"; done
exit $rc
