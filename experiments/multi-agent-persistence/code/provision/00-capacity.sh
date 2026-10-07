#!/bin/bash
# 等待区域内 vCPU 配额足够再放行。参数：NEEDED_VCPU [MAX_WAIT_SEC]
set -euo pipefail
source "$(dirname "$0")/env.sh"
NEED=$1; MAX=${2:-14400}; START=$(date +%s)
while true; do
  QUOTA=$(aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A --query 'Quota.Value' --output text | cut -d. -f1)
  USED=$(aws ec2 describe-instances --filters Name=instance-state-name,Values=pending,running --query 'Reservations[].Instances[].CpuOptions.CoreCount' --output text | tr '\t' '\n' | awk '{s+=$1*2} END {print s+0}')
  echo "$(date -u +%H:%M:%S) quota=$QUOTA used=$USED need=$NEED"
  [ $((USED + NEED)) -le "$QUOTA" ] && exit 0
  [ $(( $(date +%s) - START )) -ge "$MAX" ] && { echo "capacity wait timed out"; exit 1; }
  sleep 120
done
