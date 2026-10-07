#!/bin/bash
# 轮询某个 issue 的唤醒规则与 run，状态变化时打印一行，没有活动 run 且状态稳定 STABLE 秒后结束。参数：EXP ISSUE_ID [MAX_SEC] [STABLE_SEC]
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; ISSUE=$2; MAX=${3:-900}; STABLE=${4:-60}
START=$(date +%s); LAST=""; LASTCHANGE=$START
while true; do
  NOW=$(date +%s)
  W=$("$BUNDLE_DIR/provision/api13.sh" "$EXP" GET "/api/issues/$ISSUE/wakeups" | jq -c '[.[]? // .wakeups[]? | {fire:.fire_count,en:.enabled,pause:.paused_reason,last:.last_task_status}]')
  R=$("$BUNDLE_DIR/provision/m13.sh" "$EXP" issue runs "$ISSUE" --output json | jq -c '[.[]|{a:.agent_id[0:4],s:.status}] | group_by(.a+.s) | map({k:(.[0].a+" "+.[0].s),n:length})')
  S=$("$BUNDLE_DIR/provision/m13.sh" "$EXP" issue get "$ISSUE" --output json | jq -r .status)
  CUR="$W $R $S"
  if [ "$CUR" != "$LAST" ]; then echo "$(date +%T) status=$S wakeups=$W runs=$R"; LAST=$CUR; LASTCHANGE=$NOW; fi
  ACTIVE=$(echo "$R" | jq '[.[]|select(.k|test("running|queued|dispatched"))]|length')
  if [ "$ACTIVE" = 0 ] && [ $((NOW - LASTCHANGE)) -ge "$STABLE" ]; then echo "stable"; exit 0; fi
  [ $((NOW - START)) -ge "$MAX" ] && { echo "timeout"; exit 1; }
  sleep 15
done
