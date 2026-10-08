#!/bin/bash
# 启动一个实验的全部 EC2：multica、proxy、rt-a..rt-<n>。参数：EXP
# 所有实例使用同一个 key pair（swh30-shared）；runtime 之间的安全组互相放行 22 端口，便于 agent 之间 SSH 互登。
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1
N=$(exp_field "$EXP" n_agents)
TASK=$(exp_field "$EXP" task)
RT_TYPE=$(task_field "$TASK" instance_type)
RT_DISK=$(task_field "$TASK" disk_gb)
D=$(exp_dir "$EXP"); mkdir -p "$D/logs"
fetch_shared_key
TAGS="{Key=project,Value=swarmharm},{Key=issue,Value=$ISSUE_TAG},{Key=experiment,Value=$EXP}"
# 并行实验共用一个 vCPU 配额：用 S3 条件写入做启动锁，持锁期间等待配额并启动整套实例，避免两个实验各占一半而互相等待
LOCK_KEY=swh30/locks/launch
LOCK_FILE="$D/lock-body.txt"
HAVE_LOCK=0
release_lock() { [ "$HAVE_LOCK" = 1 ] && aws s3api delete-object --bucket "$BUCKET" --key "$LOCK_KEY" >/dev/null && HAVE_LOCK=0; return 0; }
trap release_lock EXIT
acquire_lock() {
  local waited=0
  while true; do
    echo "$EXP $(date +%s)" > "$LOCK_FILE"
    if aws s3api put-object --bucket "$BUCKET" --key "$LOCK_KEY" --body "$LOCK_FILE" --if-none-match '*' >/dev/null 2>&1; then HAVE_LOCK=1; return; fi
    # 持有者超过 15 分钟没有释放视为遗留的锁（持锁只用于检查配额与启动实例）
    local body age
    body=$(aws s3 cp --quiet "s3://$BUCKET/$LOCK_KEY" - 2>/dev/null || true)
    if [ -n "$body" ]; then
      age=$(( $(date +%s) - ${body##* } ))
      if [ "$age" -gt 900 ]; then aws s3api delete-object --bucket "$BUCKET" --key "$LOCK_KEY" >/dev/null; continue; fi
    fi
    [ $waited -lt 14400 ] || { echo "launch lock wait timed out" >&2; exit 1; }
    sleep 20; waited=$((waited + 20))
  done
}
# 先持锁检查配额；配额不足就放锁等待，足够时在持锁状态下启动整套实例
WAITED_CAPACITY=0
while true; do
  acquire_lock
  if "$(dirname "$0")/00-capacity.sh" "$EXP" 0 >"$D/logs/capacity.log" 2>&1; then break; fi
  tail -n 1 "$D/logs/capacity.log"
  release_lock
  [ $WAITED_CAPACITY -lt 14400 ] || { echo "vCPU capacity wait timed out" >&2; exit 1; }
  sleep 120; WAITED_CAPACITY=$((WAITED_CAPACITY + 120))
done
aws ec2 describe-key-pairs --key-names "$SHARED_KEY_NAME" >/dev/null
mksg() {
  local name=$1 desc=$2 id
  id=$(aws ec2 describe-security-groups --filters Name=vpc-id,Values=$VPC Name=group-name,Values=$name --query 'SecurityGroups[0].GroupId' --output text)
  if [ "$id" = "None" ]; then
    id=$(aws ec2 create-security-group --vpc-id $VPC --group-name $name --description "$desc" \
      --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=$name},$TAGS]" --query GroupId --output text)
  fi
  echo "$id"
}
SG_MULTICA=$(mksg swh30-$EXP-multica "SWH-30 $EXP Multica server")
SG_PROXY=$(mksg swh30-$EXP-proxy "SWH-30 $EXP HTTP proxy")
SG_RUNTIME=$(mksg swh30-$EXP-runtime "SWH-30 $EXP agent runtimes")
auth() { aws ec2 authorize-security-group-ingress "$@" >/dev/null 2>&1 || true; }
auth --group-id $SG_MULTICA --protocol tcp --port 22 --cidr $ADMIN_CIDR
auth --group-id $SG_MULTICA --protocol tcp --port 80 --cidr 0.0.0.0/0
auth --group-id $SG_MULTICA --protocol tcp --port 443 --cidr 0.0.0.0/0
auth --group-id $SG_PROXY --protocol tcp --port 22 --cidr $ADMIN_CIDR
auth --group-id $SG_PROXY --protocol tcp --port 3128 --source-group $SG_RUNTIME
auth --group-id $SG_RUNTIME --protocol tcp --port 22 --cidr $ADMIN_CIDR
auth --group-id $SG_RUNTIME --protocol tcp --port 22 --source-group $SG_PROXY
auth --group-id $SG_RUNTIME --protocol tcp --port 22 --source-group $SG_RUNTIME
launch() {
  local name=$1 sg=$2 type=$3 disk=$4 id credit=()
  case "$type" in t3.*) credit=(--credit-specification CpuCredits=standard) ;; esac
  id=$(aws ec2 describe-instances --filters Name=tag:Name,Values=$name Name=instance-state-name,Values=pending,running \
    --query 'Reservations[0].Instances[0].InstanceId' --output text)
  local waited=0
  while [ "$id" = "None" ]; do
    # 配额被并行实验占满时（VcpuLimitExceeded）每 2 分钟重试，最长等待 4 小时；其他错误立即退出
    if id=$(aws ec2 run-instances --image-id $AMI --instance-type $type --count 1 --key-name $SHARED_KEY_NAME \
      --client-token "$name-$(date +%s)" \
      --network-interfaces "DeviceIndex=0,SubnetId=$SUBNET,Groups=$sg,AssociatePublicIpAddress=true,DeleteOnTermination=true" \
      --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$disk,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}" \
      --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1 \
      "${credit[@]}" \
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
IDS=$(launch swh30-$EXP-multica $SG_MULTICA $SVC_TYPE 20)
ID=$(launch swh30-$EXP-proxy $SG_PROXY $SVC_TYPE 20); IDS="$IDS $ID"
for i in $(seq 1 "$N"); do ID=$(launch swh30-$EXP-rt-$(letter $i) $SG_RUNTIME $RT_TYPE $RT_DISK); IDS="$IDS $ID"; done
release_lock
aws ec2 wait instance-running --instance-ids $IDS
EIP_ALLOC=$(aws ec2 describe-addresses --filters Name=tag:Name,Values=swh30-$EXP-multica --query 'Addresses[0].AllocationId' --output text)
if [ "$EIP_ALLOC" = "None" ]; then
  # Elastic IP 配额被并行实验占满时（AddressLimitExceeded），multica 实例沿用启动时分配的公网 IP（实例不停机则地址不变）
  if EIP_ALLOC=$(aws ec2 allocate-address --domain vpc --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=swh30-$EXP-multica},$TAGS]" --query AllocationId --output text 2>"$D/logs/allocate-address.err"); then
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
