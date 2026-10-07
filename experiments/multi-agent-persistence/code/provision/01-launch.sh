#!/bin/bash
# 启动一个实验的全部 EC2：multica、proxy、rt-a..rt-<n>。参数：EXP
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1
N=$(exp_field "$EXP" n_agents)
D=$(exp_dir "$EXP"); mkdir -p "$D/logs"
KEY=swh13-$EXP-operator
TAGS="{Key=project,Value=swarmharm},{Key=issue,Value=SWH-13},{Key=experiment,Value=$EXP}"
if [ ! -f "$D/swh13-$EXP-ed25519" ]; then
  ssh-keygen -q -t ed25519 -f "$D/swh13-$EXP-ed25519" -N '' -C "$KEY"
fi
if ! aws ec2 describe-key-pairs --key-names "$KEY" >/dev/null 2>&1; then
  aws ec2 import-key-pair --key-name "$KEY" --public-key-material "fileb://$D/swh13-$EXP-ed25519.pub" \
    --tag-specifications "ResourceType=key-pair,Tags=[$TAGS]" >/dev/null
fi
mksg() {
  local name=$1 desc=$2 id
  id=$(aws ec2 describe-security-groups --filters Name=vpc-id,Values=$VPC Name=group-name,Values=$name --query 'SecurityGroups[0].GroupId' --output text)
  if [ "$id" = "None" ]; then
    id=$(aws ec2 create-security-group --vpc-id $VPC --group-name $name --description "$desc" \
      --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=$name},$TAGS]" --query GroupId --output text)
  fi
  echo "$id"
}
SG_MULTICA=$(mksg swh13-$EXP-multica "SWH-13 $EXP Multica server")
SG_PROXY=$(mksg swh13-$EXP-proxy "SWH-13 $EXP HTTP proxy")
SG_RUNTIME=$(mksg swh13-$EXP-runtime "SWH-13 $EXP agent runtimes")
auth() { aws ec2 authorize-security-group-ingress "$@" >/dev/null 2>&1 || true; }
auth --group-id $SG_MULTICA --protocol tcp --port 22 --cidr $ADMIN_CIDR
auth --group-id $SG_MULTICA --protocol tcp --port 80 --cidr 0.0.0.0/0
auth --group-id $SG_MULTICA --protocol tcp --port 443 --cidr 0.0.0.0/0
auth --group-id $SG_PROXY --protocol tcp --port 22 --cidr $ADMIN_CIDR
auth --group-id $SG_PROXY --protocol tcp --port 3128 --source-group $SG_RUNTIME
auth --group-id $SG_RUNTIME --protocol tcp --port 22 --cidr $ADMIN_CIDR
auth --group-id $SG_RUNTIME --protocol tcp --port 22 --source-group $SG_PROXY
launch() {
  local name=$1 sg=$2 id
  id=$(aws ec2 describe-instances --filters Name=tag:Name,Values=$name Name=instance-state-name,Values=pending,running \
    --query 'Reservations[0].Instances[0].InstanceId' --output text)
  local waited=0
  while [ "$id" = "None" ]; do
    # 配额被并行实验占满时（VcpuLimitExceeded）每 2 分钟重试，最长等待 4 小时；其他错误立即退出
    if id=$(aws ec2 run-instances --image-id $AMI --instance-type $TYPE --count 1 --key-name $KEY \
      --client-token "$name-$(date +%s)" \
      --network-interfaces "DeviceIndex=0,SubnetId=$SUBNET,Groups=$sg,AssociatePublicIpAddress=true,DeleteOnTermination=true" \
      --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=20,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
      --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1 \
      --credit-specification CpuCredits=standard \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$name},$TAGS]" "ResourceType=volume,Tags=[{Key=Name,Value=$name},$TAGS]" \
      --query 'Instances[0].InstanceId' --output text 2>"$D/logs/run-instances.err"); then
      break
    fi
    id=None
    grep -q VcpuLimitExceeded "$D/logs/run-instances.err" || { cat "$D/logs/run-instances.err" >&2; exit 1; }
    [ $waited -lt 14400 ] || { echo "vCPU quota wait timed out" >&2; exit 1; }
    echo "$(date -u +%H:%M:%S) vCPU quota full, waiting to launch $name" >&2
    sleep 120; waited=$((waited + 120))
  done
  echo "$id"
}
IDS=$(launch swh13-$EXP-multica $SG_MULTICA)
ID=$(launch swh13-$EXP-proxy $SG_PROXY); IDS="$IDS $ID"
for i in $(seq 1 "$N"); do ID=$(launch swh13-$EXP-rt-$(letter $i) $SG_RUNTIME); IDS="$IDS $ID"; done
aws ec2 wait instance-running --instance-ids $IDS
EIP_ALLOC=$(aws ec2 describe-addresses --filters Name=tag:Name,Values=swh13-$EXP-multica --query 'Addresses[0].AllocationId' --output text)
if [ "$EIP_ALLOC" = "None" ]; then
  # Elastic IP 配额（5 个）被并行实验占满时（AddressLimitExceeded），multica 实例沿用启动时分配的公网 IP（实例不停机则地址不变）
  if EIP_ALLOC=$(aws ec2 allocate-address --domain vpc --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=swh13-$EXP-multica},$TAGS]" --query AllocationId --output text 2>"$D/logs/allocate-address.err"); then
    :
  else
    grep -q AddressLimitExceeded "$D/logs/allocate-address.err" || { cat "$D/logs/allocate-address.err" >&2; exit 1; }
    echo "Elastic IP quota full, multica keeps its auto-assigned public IP" >&2
    EIP_ALLOC=none
  fi
fi
[ "$EIP_ALLOC" = "none" ] || aws ec2 associate-address --instance-id $(echo $IDS | cut -d' ' -f1) --allocation-id $EIP_ALLOC --allow-reassociation >/dev/null
aws ec2 wait instance-status-ok --instance-ids $IDS
aws ec2 describe-instances --instance-ids $IDS \
  --query 'Reservations[].Instances[].{name:Tags[?Key==`Name`]|[0].Value,id:InstanceId,public:PublicIpAddress,private:PrivateIpAddress,sg:SecurityGroups[0].GroupId}' \
  --output json > "$D/infra.json"
echo "EIP_ALLOC=$EIP_ALLOC SG_MULTICA=$SG_MULTICA SG_PROXY=$SG_PROXY SG_RUNTIME=$SG_RUNTIME" > "$D/infra.env"
cat "$D/infra.json"; cat "$D/infra.env"
