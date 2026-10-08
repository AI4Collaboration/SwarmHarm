#!/bin/bash
# 在本机运行：每 60 秒记录实验 issue 的 run / 唤醒规则 / 评论数量，直到所有规则结束且没有活动 run，或超时。
# 参数：EXP [MAX_SEC，默认 21600]
set -uo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; MAX=${2:-21600}; D=$(exp_dir "$EXP")
M="$BUNDLE_DIR/provision/m30.sh"; A="$BUNDLE_DIR/provision/api30.sh"
ISSUE=$(cat "$D/issue-id.txt")
START=$(date +%s); LOG="$D/monitor.log"; QUIET=0
while true; do
  # run 列表随运行变大，经文件传给 python，避免超过命令行长度上限
  "$M" "$EXP" issue runs "$ISSUE" --output json > "$D/.mon-runs.json" 2>/dev/null
  "$A" "$EXP" GET "/api/issues/$ISSUE/wakeups" > "$D/.mon-wake.json" 2>/dev/null
  "$M" "$EXP" issue get "$ISSUE" --output json > "$D/.mon-issue.json" 2>/dev/null
  LINE=$(python3 - "$D/.mon-runs.json" "$D/.mon-wake.json" "$D/.mon-issue.json" <<'PY'
import json, sys
def load(path, default):
    text = open(path).read().strip()
    return json.loads(text) if text else default
runs = load(sys.argv[1], []); runs = runs if isinstance(runs, list) else runs.get("runs", runs.get("items", []))
wake = load(sys.argv[2], [])
issue = load(sys.argv[3], {})
active = sum(1 for r in runs if r.get("status") in ("running", "queued", "pending", "dispatched", "deferred"))
rules = [(w.get("enabled"), w.get("fire_count"), w.get("max_fires"), w.get("paused_reason")) for w in wake]
live = sum(1 for w in wake if w.get("enabled"))
print(f"status={issue.get('status')} runs={len(runs)} active={active} rules_enabled={live}/{len(wake)} fires={[r[1] for r in rules]} paused={[r[3] for r in rules]}")
print("DONE" if (active == 0 and live == 0) else "GO")
PY
)
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $(echo "$LINE" | head -1)" | tee -a "$LOG"
  if [ "$(echo "$LINE" | tail -1)" = "DONE" ]; then QUIET=$((QUIET + 1)); else QUIET=0; fi
  # 连续三次（3 分钟）没有活动 run 且没有启用中的规则才算结束，避免 run 排队间隙的误判
  [ "$QUIET" -ge 3 ] && { echo "all wakeup rules ended and no active runs" | tee -a "$LOG"; break; }
  [ $(( $(date +%s) - START )) -ge "$MAX" ] && { echo "monitor timeout after $MAX s" | tee -a "$LOG"; break; }
  sleep 60
done
