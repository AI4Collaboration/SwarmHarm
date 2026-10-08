#!/bin/bash
# 在本机运行：导出实验的 Multica 侧数据（issue、评论、run、run 消息、唤醒规则与历史、时间线、附件）、
# 每台 runtime 的交付物与 agent 本地状态、proxy 的 squid 访问日志，然后用 Terminal-Bench verifier 给交付物打分。参数：EXP
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; D=$(exp_dir "$EXP"); OUT="$D/export"; mkdir -p "$OUT/multica" "$OUT/runtimes" "$OUT/proxy" "$OUT/grading"
M="$BUNDLE_DIR/provision/m30.sh"; A="$BUNDLE_DIR/provision/api30.sh"
ISSUE=$(cat "$D/issue-id.txt"); N=$(exp_field "$EXP" n_agents); TASK=$(exp_field "$EXP" task)
ROOT=$(task_field "$TASK" artifact_root); PATHS=$(task_field "$TASK" artifact_paths)
fetch_shared_key
cp "$BUNDLE_DIR/experiments.json" "$BUNDLE_DIR/tasks.json" "$D/agents.json" "$D/wakeups.json" "$D/issue-body.md" "$D/started-at.txt" "$D/monitor.log" "$OUT/" 2>/dev/null || true
"$M" "$EXP" issue get "$ISSUE" --output json > "$OUT/multica/issue.json"
"$M" "$EXP" issue comment list "$ISSUE" --output json > "$OUT/multica/comments.json"
"$M" "$EXP" issue runs "$ISSUE" --output json > "$OUT/multica/runs.json"
"$M" "$EXP" issue timeline "$ISSUE" --output json > "$OUT/multica/timeline.json" 2>/dev/null || true
"$A" "$EXP" GET "/api/issues/$ISSUE/wakeups" > "$OUT/multica/wakeups.json"
"$A" "$EXP" GET "/api/issues/$ISSUE/activities" > "$OUT/multica/activities.json" 2>/dev/null || true
mkdir -p "$OUT/multica/run-messages" "$OUT/multica/wakeup-runs"
python3 -c "import json; rows=json.load(open('$OUT/multica/runs.json')); rows=rows if isinstance(rows,list) else rows.get('runs',rows.get('items',[])); print('\n'.join(r['id'] for r in rows))" | while read -r rid; do
  "$M" "$EXP" issue run-messages "$rid" --output json > "$OUT/multica/run-messages/$rid.json" 2>/dev/null || echo "run-messages failed for $rid" >&2
done
python3 -c "import json; print('\n'.join(w['id'] for w in json.load(open('$OUT/multica/wakeups.json'))))" | while read -r wid; do
  "$A" "$EXP" GET "/api/issues/$ISSUE/wakeups/$wid/runs" > "$OUT/multica/wakeup-runs/$wid.json" 2>/dev/null || true
done
# 附件：全部下载，final.tar.gz 单独复制出来作为待评交付物
mkdir -p "$OUT/multica/attachments"
python3 - "$OUT/multica/issue.json" "$OUT/multica/comments.json" <<'PY' > "$OUT/multica/attachment-ids.txt"
import json, sys
seen = {}
for p in sys.argv[1:]:
    d = json.load(open(p))
    rows = d if isinstance(d, list) else [d]
    for row in rows:
        for a in row.get("attachments", []) or []:
            seen[a["id"]] = (a.get("filename"), a.get("created_at"))
for k, (f, t) in sorted(seen.items(), key=lambda kv: kv[1][1] or ""):
    print(k, f, t)
PY
while read -r aid fname ts; do
  [ -z "$aid" ] && continue
  mkdir -p "$OUT/multica/attachments/$aid"
  "$M" "$EXP" attachment download "$aid" -o "$OUT/multica/attachments/$aid" >/dev/null 2>&1 || echo "attachment $aid download failed" >&2
done < "$OUT/multica/attachment-ids.txt"
FINAL=$(find "$OUT/multica/attachments" -name final.tar.gz | xargs -r ls -t | head -1)
# 每台 runtime：交付物（任务要求的文件）、任务目录清单、agent 的 Multica/Codex/Claude 本地状态、journal、防火墙与 sudo / SSH 记录
SSH=$(exp_ssh "$EXP")
for i in $(seq 1 "$N"); do
  L=$(letter $i); H=$(host_field "$EXP" "rt-$L" public); R="$OUT/runtimes/rt-$L"; mkdir -p "$R"
  $SSH ubuntu@$H "sudo tar czf - -C $ROOT $PATHS" > "$R/artifact.tar.gz" 2> "$R/artifact.err" || echo "artifact export failed on rt-$L" >&2
  $SSH ubuntu@$H "sudo ls -laR --time-style=full-iso $ROOT 2>/dev/null | grep -v '^total' | head -3000; echo; sudo ls -la --time-style=full-iso /home/agent /home/agent/.ssh" > "$R/project-listing.txt" 2>&1 || true
  $SSH ubuntu@$H 'sudo journalctl -u multica-runtime --no-pager -o short-iso' > "$R/multica-runtime.journal" 2>&1 || true
  $SSH ubuntu@$H 'sudo cat /home/agent/.multica/daemon.log 2>/dev/null' > "$R/daemon.log" 2>&1 || true
  # agent 本地状态以目录形式导出（凭据扫描需要能读到内容）：~/multica_workspaces 下每个 run 的 codex-home/claude 会话文件在其中；
  # 含密钥的三个配置文件由 runtime-config.sh 生成，内容已知，不导出；SSH 私钥不导出
  mkdir -p "$R/agent-home"
  # 大于 20 MB 的文件（例如 agent 生成的完整数据集输出）不导出，只在 big-files.txt 里记录路径和大小
  $SSH ubuntu@$H 'sudo find /home/agent/.multica /home/agent/.codex /home/agent/.claude /home/agent/multica_workspaces -type f -size +20M -printf "%p %s\n"' > "$R/big-files.txt" 2>/dev/null || true
  $SSH ubuntu@$H 'sudo bash -c "cd /home/agent && { find .multica .codex .claude multica_workspaces -type f -size -21M ! -path .multica/config.json ! -path .claude/settings.json ! -path .codex/config.toml; ls -1 .claude.json .bash_history .ssh/known_hosts 2>/dev/null; } | tar czf - -T - 2>/dev/null"' | tar xzf - -C "$R/agent-home" 2>/dev/null || true
  # auth.log 只保留 agent 用户的 sudo 记录与 sshd 的公钥登录记录，且限于实验开始之后，再对凭据形态的字符串做替换
  $SSH ubuntu@$H "sudo ufw status verbose; echo; sudo grep -hE 'sudo: *agent :|sshd.*Accepted publickey' /var/log/auth.log 2>/dev/null | awk -v s='$(cat "$D/started-at.txt")' '\$1 >= s' | tail -3000" 2>&1 | sed -E 's/(ah-[0-9a-f]{20,}|mul_[0-9a-f]{20,}|mat_[A-Za-z0-9_-]{20,})/[redacted-credential]/g' > "$R/firewall-sudo-ssh.txt" || true
done
# proxy：squid 访问日志（记录每一次经代理的请求，含被拒绝的目标）
PH=$(host_field "$EXP" proxy public)
$SSH ubuntu@$PH 'sudo cat /var/log/squid/access.log' > "$OUT/proxy/squid-access-all.log" 2>/dev/null || true
# squid 日志第一列是 epoch 秒；squid-access.log 只含任务 issue 创建之后的请求
START_EPOCH=$(date -u -d "$(cat "$D/started-at.txt")" +%s)
awk -v s="$START_EPOCH" '$1 >= s' "$OUT/proxy/squid-access-all.log" > "$OUT/proxy/squid-access.log"
# 打分：final.tar.gz（若有）以及每台 runtime 的交付物
if [ -n "$FINAL" ]; then
  cp "$FINAL" "$OUT/grading/final.tar.gz"
  "$BUNDLE_DIR/provision/grade.sh" "$TASK" "$OUT/grading/final.tar.gz" "$OUT/grading/final" | tee "$OUT/grading/final.summary"
else
  echo "no final.tar.gz attachment" | tee "$OUT/grading/final.summary"
fi
for i in $(seq 1 "$N"); do
  L=$(letter $i); P="$OUT/runtimes/rt-$L/artifact.tar.gz"
  if [ -s "$P" ]; then "$BUNDLE_DIR/provision/grade.sh" "$TASK" "$P" "$OUT/grading/rt-$L" | tee "$OUT/grading/rt-$L.summary"; fi
done
du -sh "$OUT"
