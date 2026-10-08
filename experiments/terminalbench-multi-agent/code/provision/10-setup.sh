#!/bin/bash
# 在本机运行：从零搭建一个实验的全部基础设施（网络仍开放的阶段）。参数：EXP
# 顺序：启动 EC2 -> 并行（Multica 服务器与 admin 账号 | proxy | 每台 runtime 的基础软件、SSH 密钥、任务环境）
#       -> AxonHub key -> 每台 runtime 的 harness 配置与 daemon -> 创建 agent 与 squad。
# 前置：.scratch/swh6-ed25519（SWH-6 附件 swarmharm-handover.tar.gz 里的 meta host 密钥）。
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; D=$(exp_dir "$EXP"); mkdir -p "$D/logs"
N=$(exp_field "$EXP" n_agents); TASK=$(exp_field "$EXP" task); HARNESS=$(exp_field "$EXP" harness); MODEL=$(exp_field "$EXP" model)
META_KEY="$BUNDLE_DIR/.scratch/swh6-ed25519"
test -f "$META_KEY"
fetch_shared_key
"$BUNDLE_DIR/provision/01-launch.sh" "$EXP" > "$D/logs/launch.log" 2>&1 || { tail -n 20 "$D/logs/launch.log"; exit 1; }
SSH=$(exp_ssh "$EXP")
EIP=$(host_field "$EXP" multica public)
PH=$(host_field "$EXP" proxy public)
PP=$(host_field "$EXP" proxy private)
PEERS=()
for i in $(seq 1 "$N"); do PEERS+=("dev-$(letter $i)=$(host_field "$EXP" "rt-$(letter $i)" private)"); done

setup_multica() {
  IMAGE_URL=$(aws s3 presign "s3://$BUCKET/$MULTICA_IMAGE_KEY" --expires-in 3600)
  $SSH ubuntu@$EIP "sudo bash -s $EIP $ACME_EMAIL $ADMIN_EMAIL $ADMIN_CIDR '$IMAGE_URL'" < "$BUNDLE_DIR/provision/multica-server.sh"
  "$BUNDLE_DIR/provision/02-multica-account.sh" "$EXP"
}
setup_proxy() {
  $SSH ubuntu@$PH "sudo bash -s $EIP $AXONHUB_HOST $RUNTIME_CIDR $ADMIN_CIDR" < "$BUNDLE_DIR/provision/proxy.sh"
}
setup_runtime() {
  local i=$1 L H
  L=$(letter "$i"); H=$(host_field "$EXP" "rt-$L" public)
  $SSH ubuntu@$H "sudo bash -s $PP" < "$BUNDLE_DIR/provision/runtime-base.sh"
  scp -q -i "$SHARED_KEY" -o StrictHostKeyChecking=accept-new "$SHARED_KEY" ubuntu@$H:/home/ubuntu/swh30-key
  scp -q -i "$SHARED_KEY" -o StrictHostKeyChecking=accept-new "$SHARED_KEY.pub" ubuntu@$H:/home/ubuntu/swh30-key.pub
  local others=()
  for p in "${PEERS[@]}"; do [ "${p%%=*}" = "dev-$L" ] || others+=("$p"); done
  $SSH ubuntu@$H "sudo bash -s dev-$L ${others[*]}" < "$BUNDLE_DIR/provision/runtime-ssh.sh"
  # 任务环境：只上传 environment/（相当于容器镜像的构建上下文）；tests/ 与 solution/ 保留在本机
  $SSH ubuntu@$H 'sudo rm -rf /opt/swh30 && sudo mkdir -p /opt/swh30/task && sudo chmod 755 /opt/swh30 /opt/swh30/task && sudo chown ubuntu /opt/swh30/task'
  scp -q -r -i "$SHARED_KEY" -o StrictHostKeyChecking=accept-new "$BUNDLE_DIR/tasks/$TASK/environment" ubuntu@$H:/opt/swh30/task/
  $SSH ubuntu@$H "sudo bash -s $TASK" < "$BUNDLE_DIR/provision/task-env.sh"
}
PIDS=(); NAMES=()
# 重新运行时可设置 SKIP_SERVICES=1，跳过已经完成的 Multica 服务器与 proxy 部分
if [ "${SKIP_SERVICES:-0}" != 1 ]; then
  ( setup_multica > "$D/logs/setup-multica.log" 2>&1 ) & PIDS+=($!); NAMES+=(multica)
  ( setup_proxy > "$D/logs/setup-proxy.log" 2>&1 ) & PIDS+=($!); NAMES+=(proxy)
fi
for i in $(seq 1 "$N"); do
  ( setup_runtime "$i" > "$D/logs/setup-rt-$(letter "$i").log" 2>&1 ) & PIDS+=($!); NAMES+=("rt-$(letter "$i")")
done
FAILED=0
for k in "${!PIDS[@]}"; do
  if wait "${PIDS[$k]}"; then echo "setup ${NAMES[$k]}: ok"; else echo "setup ${NAMES[$k]}: exit code != 0, see $D/logs/setup-${NAMES[$k]}.log"; FAILED=1; fi
done
[ $FAILED = 0 ] || exit 1

# AxonHub：每台 runtime 一个独立的 key，便于在 AxonHub 日志中区分来源
KEYNAMES=(); for i in $(seq 1 "$N"); do KEYNAMES+=("swh30-$EXP-rt-$(letter "$i")"); done
scp -q -i "$META_KEY" -o StrictHostKeyChecking=accept-new "$BUNDLE_DIR/provision/axonhub-keys.py" ubuntu@$META_HOST:/tmp/swh30-axonhub-keys.py
ssh -i "$META_KEY" ubuntu@$META_HOST "sudo python3 /tmp/swh30-axonhub-keys.py create gid://axonhub/Project/1 ${KEYNAMES[*]}" > "$D/axonhub-keys.json"
chmod 600 "$D/axonhub-keys.json"
PAT=$(jq -r .pat "$D/multica-account.json"); WS=$(jq -r .workspace.id "$D/multica-account.json")
config_runtime() {
  local i=$1 L H KEY
  L=$(letter "$i"); H=$(host_field "$EXP" "rt-$L" public); KEY=$(jq -r ".\"swh30-$EXP-rt-$L\"" "$D/axonhub-keys.json")
  $SSH ubuntu@$H "sudo bash -s swh30-$EXP-rt-$L $PP https://$EIP $PAT $WS $KEY $HARNESS $MODEL" < "$BUNDLE_DIR/provision/runtime-config.sh"
}
PIDS=()
for i in $(seq 1 "$N"); do ( config_runtime "$i" > "$D/logs/config-rt-$(letter "$i").log" 2>&1 ) & PIDS+=($!); done
FAILED=0
for k in "${!PIDS[@]}"; do
  if wait "${PIDS[$k]}"; then echo "config rt-$(letter $((k + 1))): ok"; else echo "config rt-$(letter $((k + 1))): failed, see $D/logs/config-rt-$(letter $((k + 1))).log"; FAILED=1; fi
done
[ $FAILED = 0 ] || exit 1
sleep 15
"$BUNDLE_DIR/provision/create-agents.sh" "$EXP" > "$D/logs/create-agents.log" 2>&1 || { tail -n 20 "$D/logs/create-agents.log"; exit 1; }
echo "setup of $EXP complete"; cat "$D/infra.json" | jq -r '.[].name'
