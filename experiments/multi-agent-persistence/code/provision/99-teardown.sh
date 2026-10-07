#!/bin/bash
# 拆除一个实验的全部 AWS 资源（只处理带 experiment=<EXP> 标签的资源），最后做核对。参数：EXP
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1
F="Name=tag:experiment,Values=$EXP"
INSTANCES=$(aws ec2 describe-instances --filters "$F" Name=instance-state-name,Values=pending,running,stopping,stopped --query 'Reservations[].Instances[].InstanceId' --output text)
if [ -n "$INSTANCES" ]; then
  echo "terminating: $INSTANCES"
  aws ec2 terminate-instances --instance-ids $INSTANCES --query 'TerminatingInstances[].[InstanceId,CurrentState.Name]' --output text
  aws ec2 wait instance-terminated --instance-ids $INSTANCES
fi
for alloc in $(aws ec2 describe-addresses --filters "$F" --query 'Addresses[].AllocationId' --output text); do
  aws ec2 release-address --allocation-id "$alloc"; echo "released $alloc"
done
SG_RUNTIME=$(aws ec2 describe-security-groups --filters "$F" Name=group-name,Values=swh13-$EXP-runtime --query 'SecurityGroups[0].GroupId' --output text)
SG_PROXY=$(aws ec2 describe-security-groups --filters "$F" Name=group-name,Values=swh13-$EXP-proxy --query 'SecurityGroups[0].GroupId' --output text)
SG_MULTICA=$(aws ec2 describe-security-groups --filters "$F" Name=group-name,Values=swh13-$EXP-multica --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG_RUNTIME" != None ] && [ "$SG_PROXY" != None ]; then
  aws ec2 revoke-security-group-egress --group-id "$SG_RUNTIME" --ip-permissions "IpProtocol=tcp,FromPort=3128,ToPort=3128,UserIdGroupPairs=[{GroupId=$SG_PROXY}]" >/dev/null 2>&1 || true
  aws ec2 revoke-security-group-ingress --group-id "$SG_PROXY" --ip-permissions "IpProtocol=tcp,FromPort=3128,ToPort=3128,UserIdGroupPairs=[{GroupId=$SG_RUNTIME}]" >/dev/null 2>&1 || true
  aws ec2 revoke-security-group-ingress --group-id "$SG_RUNTIME" --ip-permissions "IpProtocol=tcp,FromPort=22,ToPort=22,UserIdGroupPairs=[{GroupId=$SG_PROXY}]" >/dev/null 2>&1 || true
fi
for sg in "$SG_RUNTIME" "$SG_PROXY" "$SG_MULTICA"; do
  [ "$sg" != None ] && { aws ec2 delete-security-group --group-id "$sg"; echo "deleted $sg"; }
done
aws ec2 delete-key-pair --key-name "swh13-$EXP-operator" && echo "deleted key pair swh13-$EXP-operator"
echo "## verification for $EXP"
echo "instances:" $(aws ec2 describe-instances --filters "$F" Name=instance-state-name,Values=pending,running,stopping,stopped --query 'Reservations[].Instances[].InstanceId' --output text)
echo "volumes:" $(aws ec2 describe-volumes --filters "$F" --query 'Volumes[].VolumeId' --output text)
echo "addresses:" $(aws ec2 describe-addresses --filters "$F" --query 'Addresses[].AllocationId' --output text)
echo "security groups:" $(aws ec2 describe-security-groups --filters "$F" --query 'SecurityGroups[].GroupId' --output text)
echo "key pairs:" $(aws ec2 describe-key-pairs --filters "$F" --query 'KeyPairs[].KeyName' --output text)
echo "remaining SWH-13 instances in region:"
aws ec2 describe-instances --filters Name=tag:issue,Values=SWH-13 Name=instance-state-name,Values=pending,running,stopping,stopped --query 'Reservations[].Instances[].[InstanceId,State.Name,Tags[?Key==`Name`]|[0].Value]' --output text
echo "all unattached volumes:" $(aws ec2 describe-volumes --filters Name=status,Values=available --query 'Volumes[].VolumeId' --output text)
echo "all unassociated addresses:" $(aws ec2 describe-addresses --query 'Addresses[?AssociationId==`null`].AllocationId' --output text)
