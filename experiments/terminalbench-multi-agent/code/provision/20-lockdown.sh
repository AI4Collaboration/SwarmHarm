#!/bin/bash
# 在本机运行：给一个实验的 runtime 施加网络限制。参数：EXP
# 安全组出站只放行 proxy:3128 与同实验 runtime 之间的 22；每台 runtime 的 UFW 同样只放行这两类流量。
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; D=$(exp_dir "$EXP"); N=$(exp_field "$EXP" n_agents)
fetch_shared_key
source "$D/infra.env"
SSH=$(exp_ssh "$EXP")
PP=$(host_field "$EXP" proxy private)
aws ec2 revoke-security-group-egress --group-id $SG_RUNTIME --ip-permissions 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}]' >/dev/null
aws ec2 authorize-security-group-egress --group-id $SG_RUNTIME --ip-permissions "IpProtocol=tcp,FromPort=3128,ToPort=3128,UserIdGroupPairs=[{GroupId=$SG_PROXY}]" >/dev/null
aws ec2 authorize-security-group-egress --group-id $SG_RUNTIME --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,UserIdGroupPairs=[{GroupId=$SG_RUNTIME}]" >/dev/null
PEER_IPS=(); for i in $(seq 1 "$N"); do PEER_IPS+=("$(host_field "$EXP" "rt-$(letter "$i")" private)"); done
for i in $(seq 1 "$N"); do
  H=$(host_field "$EXP" "rt-$(letter "$i")" public)
  # 启用 UFW 会中断当前 SSH 连接，所以带超时运行并忽略退出码，随后重新连接核对
  timeout 60 $SSH ubuntu@$H "sudo bash -s $PP $ADMIN_CIDR ${PEER_IPS[*]}" < "$BUNDLE_DIR/provision/runtime-lockdown.sh" || true
  $SSH ubuntu@$H 'sudo ufw status verbose' | tee "$D/logs/ufw-rt-$(letter "$i").txt"
done
aws ec2 describe-security-groups --group-ids $SG_RUNTIME --query 'SecurityGroups[0].IpPermissionsEgress' --output json | tee "$D/logs/sg-runtime-egress.json"
