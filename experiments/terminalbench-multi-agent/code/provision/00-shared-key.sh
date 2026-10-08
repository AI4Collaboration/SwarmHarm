#!/bin/bash
# 创建（或确认存在）所有 SWH-30 实验共用的 SSH 密钥：本地生成密钥对，私钥与公钥上传到 S3，公钥导入为 EC2 key pair swh30-shared。
# 98-final-cleanup.sh 会把它们全部删除；之后的新实验（例如计划中的 GLM 实验）先运行本脚本。
set -euo pipefail
source "$(dirname "$0")/env.sh"
if aws s3api head-object --bucket "$BUCKET" --key swh30/ssh/swh30-shared-ed25519 >/dev/null 2>&1; then
  fetch_shared_key
else
  mkdir -p "$(dirname "$SHARED_KEY")"
  rm -f "$SHARED_KEY" "$SHARED_KEY.pub"
  ssh-keygen -q -t ed25519 -N '' -C swh30-shared -f "$SHARED_KEY"
  aws s3 cp --quiet "$SHARED_KEY" "s3://$BUCKET/swh30/ssh/swh30-shared-ed25519"
  aws s3 cp --quiet "$SHARED_KEY.pub" "s3://$BUCKET/swh30/ssh/swh30-shared-ed25519.pub"
fi
if ! aws ec2 describe-key-pairs --key-names "$SHARED_KEY_NAME" >/dev/null 2>&1; then
  aws ec2 import-key-pair --key-name "$SHARED_KEY_NAME" --public-key-material "fileb://$SHARED_KEY.pub" \
    --tag-specifications "ResourceType=key-pair,Tags=[{Key=project,Value=swarmharm},{Key=issue,Value=$ISSUE_TAG}]" >/dev/null
fi
aws ec2 describe-key-pairs --key-names "$SHARED_KEY_NAME" --query 'KeyPairs[0].[KeyName,KeyFingerprint]' --output text
