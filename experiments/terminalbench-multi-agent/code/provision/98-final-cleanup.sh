#!/bin/bash
# 整个 SWH-30 系列结束后运行：删除共享 key pair 与 S3 上的共享私钥，并核对区域内没有残留的计费资源。
set -euo pipefail
source "$(dirname "$0")/env.sh"
LEFT=$(aws ec2 describe-instances --filters Name=tag:issue,Values=$ISSUE_TAG Name=instance-state-name,Values=pending,running,stopping,stopped --query 'Reservations[].Instances[].InstanceId' --output text)
[ -z "$LEFT" ] || { echo "instances of $ISSUE_TAG still exist: $LEFT"; exit 1; }
aws ec2 delete-key-pair --key-name "$SHARED_KEY_NAME" && echo "deleted key pair $SHARED_KEY_NAME"
aws s3 rm --recursive --quiet "s3://$BUCKET/swh30/ssh/" && echo "removed shared private key from S3"
echo "instances (all, non-terminated):"
aws ec2 describe-instances --filters Name=instance-state-name,Values=pending,running,stopping,stopped --query 'Reservations[].Instances[].[InstanceId,InstanceType,State.Name,Tags[?Key==`Name`]|[0].Value]' --output text
echo "volumes:"; aws ec2 describe-volumes --query 'Volumes[].[VolumeId,Size,State,Tags[?Key==`Name`]|[0].Value]' --output text
echo "addresses:"; aws ec2 describe-addresses --query 'Addresses[].[AllocationId,PublicIp,AssociationId]' --output text
echo "security groups tagged $ISSUE_TAG:" $(aws ec2 describe-security-groups --filters Name=tag:issue,Values=$ISSUE_TAG --query 'SecurityGroups[].GroupId' --output text)
echo "key pairs:" $(aws ec2 describe-key-pairs --query 'KeyPairs[].KeyName' --output text)
