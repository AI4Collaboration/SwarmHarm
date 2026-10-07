#!/bin/bash
# 在本机运行：生成任务 issue 正文，创建 issue，指派给 Dev Team，并以 admin 身份为每个 agent 建立
# “有 run 结束就唤醒”的规则（continuous，max_fires=20）。参数：EXP
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; D=$(exp_dir "$EXP")
TASK=$(exp_field "$EXP" task); N=$(exp_field "$EXP" n_agents)
M="$BUNDLE_DIR/provision/m13.sh"
# 队长的 run 只在 issue 创建时、runtime 在线的情况下才会入队：先等绑定的所有 runtime 都在线
for _ in $(seq 1 30); do
  OFFLINE=$("$M" "$EXP" runtime list --output json | python3 -c "
import json, sys
bound = {a['runtime_id'] for a in json.load(open('$D/agents.json'))['agents'].values()}
print(sum(1 for r in json.load(sys.stdin) if r['id'] in bound and r['status'] != 'online'))")
  [ "$OFFLINE" = 0 ] && break
  sleep 10
done
[ "$OFFLINE" = 0 ] || { echo "bound runtimes are not online"; exit 1; }
python3 "$BUNDLE_DIR/prompts/render.py" "$TASK" "$N" > "$D/issue-body.md"
TITLE=$(head -1 "$D/issue-body.md" | sed 's/^# //')
tail -n +3 "$D/issue-body.md" > "$D/issue-description.md"
SQUAD=$(python3 -c "import json;print(json.load(open('$D/agents.json'))['squad_id'])")
ISSUE=$("$M" "$EXP" issue create --title "$TITLE" --description-file "$D/issue-description.md" --status todo --assignee-id "$SQUAD" --output json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
echo "$ISSUE" > "$D/issue-id.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$D/started-at.txt"
# 唤醒规则由 admin（人类）创建；服务端 patch 保证 agent 无法更改或关闭
python3 - "$D" > "$D/wakeups.json" <<'PY'
import json, subprocess, sys
d = sys.argv[1]
exp = d.rstrip("/").split("/")[-1]
agents = json.load(open(f"{d}/agents.json"))["agents"]
issue = open(f"{d}/issue-id.txt").read().strip()
m = f"{d}/../../provision/m13.sh"
out = {}
for name, a in agents.items():
    r = subprocess.run([m, exp, "issue", "wakeup", "create", issue, "--agent-id", a["agent_id"], "--kind", "event",
                        "--event", "task.completed,task.failed,task.cancelled", "--mode", "continuous", "--max-fires", "20",
                        "--instruction-file", f"{d}/../../prompts/wakeup-instruction.md", "--output", "json"], capture_output=True, text=True, check=True)
    out[name] = json.loads(r.stdout)
print(json.dumps(out, indent=1))
PY
python3 -c "import json; d=json.load(open('$D/wakeups.json')); print({k:(v.get('id'), v.get('enabled'), v.get('max_fires'), v.get('mode')) for k,v in d.items()})"
echo "issue=$ISSUE"
