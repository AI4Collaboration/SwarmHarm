#!/bin/bash
# RUNBOOK 第 6 节：收紧 runtime 安全组出口（只放行到 proxy 的 3128）并在每台 runtime 上启用 UFW 限制。参数：EXP
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1
N=$(exp_field "$EXP" n_agents)
source "$(exp_dir "$EXP")/infra.env"
PP=$(host_field "$EXP" proxy private)
SSH=$(exp_ssh "$EXP")
aws ec2 revoke-security-group-egress --group-id "$SG_RUNTIME" --ip-permissions 'IpProtocol=-1,IpRanges=[{CidrIp=0.0.0.0/0}]' >/dev/null
aws ec2 authorize-security-group-egress --group-id "$SG_RUNTIME" --ip-permissions "IpProtocol=tcp,FromPort=3128,ToPort=3128,UserIdGroupPairs=[{GroupId=$SG_PROXY}]" >/dev/null
for i in $(seq 1 "$N"); do
  L=$(letter "$i"); H=$(host_field "$EXP" rt-$L public)
  echo "##### rt-$L lockdown"
  timeout 60 $SSH ubuntu@$H "sudo bash -s $PP $ADMIN_CIDR" < "$(dirname "$0")/runtime-lockdown.sh" || true
  $SSH ubuntu@$H 'sudo ufw status verbose'
done
