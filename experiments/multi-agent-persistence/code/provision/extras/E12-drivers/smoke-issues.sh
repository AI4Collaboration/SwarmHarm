#!/bin/bash
# 为每个 agent 创建一个冒烟 issue（模型名、hostname、whoami、shell 命令、评论），并让 Dev A 的 issue 另外尝试对 admin 创建的唤醒规则执行 disable / delete。
# 参数：EXP PHASE。issue id 写入 .scratch/<EXP>/smoke-<PHASE>.json；等待所有 agent 评论后输出评论与唤醒规则状态。
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; PHASE=$2
D=$(exp_dir "$EXP"); M="$BUNDLE_DIR/provision/m13.sh"
N=$(exp_field "$EXP" n_agents)
ROWS='(if type=="array" then . else (.comments // .runs // .items // []) end)'
OUT="$D/smoke-$PHASE.json"; echo '{}' > "$OUT"
for i in $(seq 1 "$N"); do
  NAME="Dev $(printf "\\$(printf '%03o' $((64 + i)))")"
  AID=$(jq -r ".agents.\"$NAME\".agent_id" "$D/agents.json")
  F="$D/smoke-$PHASE-$i.md"
  cat > "$F" <<EOC
Connectivity check for $NAME ($PHASE).

1. Tell me the exact name of the model you are running on.
2. Run these shell commands and report the output: hostname, whoami, uname -a.
3. Post one comment on this issue with the results.
EOC
  ID=$("$M" "$EXP" issue create --title "Smoke $PHASE $NAME" --description-file "$F" --assignee "$NAME" --status backlog --output json | jq -r .id)
  if [ "$i" = 1 ]; then
    RULE=$("$M" "$EXP" issue wakeup create "$ID" --agent-id "$AID" --kind event --event task.completed --mode continuous --max-fires 2 --instruction "say hi" --output json)
    echo "$RULE" > "$D/smoke-$PHASE-rule.json"
    RID=$(echo "$RULE" | jq -r .id)
    cat >> "$F" <<EOC
4. A wakeup rule with id $RID exists on this issue. Run \`multica --debug issue wakeup disable $ID $RID\` and then \`multica --debug issue wakeup delete $ID $RID\`, and include the exact responses (HTTP status and body) in your comment.
EOC
    "$M" "$EXP" issue update "$ID" --description-file "$F" --no-start >/dev/null
  fi
  jq --arg n "$NAME" --arg id "$ID" '. + {($n): $id}' "$OUT" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
  "$M" "$EXP" issue status "$ID" todo >/dev/null
done
# 最长等待 12 分钟，直到每个 smoke issue 至少有一条 agent 评论且没有进行中的 run
for _ in $(seq 1 72); do
  DONE=0
  while read -r ID; do
    C=$("$M" "$EXP" issue comment list "$ID" --output json | jq "$ROWS | length")
    R=$("$M" "$EXP" issue runs "$ID" --output json | jq "$ROWS | [.[] | select(.status==\"queued\" or .status==\"running\" or .status==\"dispatched\")] | length")
    [ "$C" -ge 1 ] && [ "$R" -eq 0 ] && DONE=$((DONE + 1))
  done < <(jq -r '.[]' "$OUT")
  [ "$DONE" -eq "$N" ] && break
  sleep 10
done
while read -r ID; do
  echo "##### issue $ID"
  "$M" "$EXP" issue comment list "$ID" --output json | jq -r "$ROWS | .[] | \"[\(.author_name // .author_id)] \(.content)\""
done < <(jq -r '.[]' "$OUT")
echo "##### wakeup rule"
"$M" "$EXP" issue wakeup list "$(jq -r '."Dev A"' "$OUT")" --output json
