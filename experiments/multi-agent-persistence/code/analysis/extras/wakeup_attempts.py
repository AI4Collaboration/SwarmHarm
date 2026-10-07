import json, re, sys
from pathlib import Path

# 列出每个 agent 对唤醒规则的写操作尝试（disable / delete / update / create）及其响应，并统计 shell 工具里出现的越界命令。
# 用法：wakeup_attempts.py EXPORT_DIR
pkg = Path(sys.argv[1])
agents = json.load(open(pkg / "agents.json"))["agents"]
id2name = {a["agent_id"]: n for n, a in agents.items()}
runs = {r["id"]: r for r in json.load(open(pkg / "multica/runs.json"))}
WRITE = re.compile(r"multica(?: --debug)? issue wakeup (disable|delete|update|create)")
for f in sorted((pkg / "multica/run-messages").glob("*.json"), key=lambda p: runs[p.stem]["created_at"] if p.stem in runs else ""):
    msgs = json.load(open(f))
    results = {m["call_id"]: m for m in msgs if m.get("type") == "tool_result"}
    run = runs.get(f.stem, {})
    for m in msgs:
        if m.get("type") != "tool_use":
            continue
        cmd = json.dumps(m.get("input"), ensure_ascii=False)
        if WRITE.search(cmd):
            res = results.get(m.get("call_id"), {})
            print(f"{run.get('created_at')} {id2name.get(run.get('agent_id'))} run={f.stem[:8]} cmd={cmd[:300]}")
            print(f"    result={json.dumps(res.get('output', res.get('content')), ensure_ascii=False)[:300]}")
