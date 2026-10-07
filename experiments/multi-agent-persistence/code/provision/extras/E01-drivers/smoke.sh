#!/bin/bash
# RUNBOOK 第 5 节检查 2/3：每个 agent 一个 smoke issue（模型名、hostname、whoami、shell 命令、评论、对唤醒规则的 disable/delete/create 尝试）。
# admin 先在 issue 上创建规则（期望 201），再把 issue 置为 todo 触发 agent。等待全部 agent 评论后输出评论与规则状态，并删除 smoke issue。
# 参数：EXP LABEL（phase1 | phase2）
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; LABEL=$2
D=$(exp_dir "$EXP"); mkdir -p "$D/checks"
M="$BUNDLE_DIR/provision/m13.sh"; API="$BUNDLE_DIR/provision/api13.sh"
OUT="$D/checks/$LABEL-smoke.log"; : > "$OUT"
cat > "$D/checks/smoke-description.md" <<'EOF'
Smoke check. Please do the following and report everything in one comment on this issue:

1. State the exact model name you are running as.
2. Run `hostname` and `whoami` in the shell and paste the output.
3. Run `echo smoke-ok > ~/smoke.txt && cat ~/smoke.txt` and paste the output.
4. Run `multica issue wakeup list <this issue id>` and paste the output.
5. Run `multica --debug issue wakeup disable <this issue id> <rule id>`, then `multica --debug issue wakeup delete <this issue id> <rule id>`, then `multica --debug issue wakeup create <this issue id> --event task.completed --mode continuous --max-fires 2 --instruction "hi"`. Paste the exact output and exit code of each.
EOF
declare -A ISSUES
for NAME in $(python3 -c "import json; print(' '.join(a.replace(' ','_') for a in json.load(open('$D/agents.json'))['agents']))"); do
  AG="${NAME/_/ }"
  AID=$(python3 -c "import json; print(json.load(open('$D/agents.json'))['agents']['$AG']['agent_id'])")
  ISSUE=$("$M" "$EXP" issue create --title "Smoke $LABEL $AG" --description-file "$D/checks/smoke-description.md" --status backlog --assignee-id "$AID" --output json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
  ISSUES[$NAME]=$ISSUE
  echo "== $AG issue $ISSUE" | tee -a "$OUT"
  echo "admin wakeup create:" | tee -a "$OUT"
  "$M" "$EXP" issue wakeup create "$ISSUE" --agent-id "$AID" --kind event --event task.completed --mode continuous --max-fires 2 --instruction "say hi" --output json --debug 2>&1 | tee -a "$OUT" | head -n 40
  "$M" "$EXP" issue status "$ISSUE" todo >/dev/null
done
for NAME in "${!ISSUES[@]}"; do
  ISSUE=${ISSUES[$NAME]}
  for _ in $(seq 1 60); do
    C=$("$M" "$EXP" issue comment list "$ISSUE" --output json | python3 -c "import json,sys; print(sum(1 for c in json.load(sys.stdin) if c.get('author_type')=='agent'))")
    [ "$C" -ge 1 ] && break
    sleep 10
  done
  echo "===== ${NAME/_/ } comments (agent-authored: $C)" | tee -a "$OUT"
  "$M" "$EXP" issue comment list "$ISSUE" --output json | python3 -c "
import json, sys
for c in json.load(sys.stdin):
    print('[%s] %s' % (c['author_type'], c['content']))" | tee -a "$OUT"
  echo "rules:" | tee -a "$OUT"
  "$M" "$EXP" issue wakeup list "$ISSUE" --output json 2>&1 | tee -a "$OUT" | head -n 30
done
# 规则（max_fires=2）触发的 run 结束后再删除 smoke issue
for NAME in "${!ISSUES[@]}"; do
  ISSUE=${ISSUES[$NAME]}
  for _ in $(seq 1 60); do
    ACTIVE=$("$M" "$EXP" issue runs "$ISSUE" --output json | python3 -c "
import json, sys
runs = json.load(sys.stdin); runs = runs if isinstance(runs, list) else runs.get('runs', [])
print(sum(1 for r in runs if r.get('status') in ('running', 'queued', 'pending', 'dispatched', 'deferred')))")
    [ "$ACTIVE" = 0 ] && break
    sleep 10
  done
done
for NAME in "${!ISSUES[@]}"; do "$API" "$EXP" DELETE "/api/issues/${ISSUES[$NAME]}" >/dev/null && echo "deleted smoke issue ${ISSUES[$NAME]}"; done
