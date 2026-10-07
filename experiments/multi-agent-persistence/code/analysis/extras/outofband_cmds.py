import json, re, sys
from pathlib import Path

# 在 run 消息的 shell 命令中查找联网相关命令（pip、curl、wget、git clone/fetch、npm、uv）。用法：outofband_cmds.py EXPORT_DIR
pkg = Path(sys.argv[1])
agents = json.load(open(pkg / "agents.json"))["agents"]
id2name = {a["agent_id"]: n for n, a in agents.items()}
runs = {r["id"]: r for r in json.load(open(pkg / "multica/runs.json"))}
PAT = re.compile(r"\b(pip3? install|python3? -m pip|uv pip|uv sync|curl |wget |git (clone|fetch|pull|ls-remote)|npm (install|i) |github\.com|pypi\.org|api\.anthropic)")
for f in sorted((pkg / "multica/run-messages").glob("*.json"), key=lambda p: runs[p.stem]["created_at"] if p.stem in runs else ""):
    run = runs.get(f.stem, {})
    for m in json.load(open(f)):
        if m.get("type") == "tool_use":
            cmd = (m.get("input") or {}).get("command", "") if isinstance(m.get("input"), dict) else ""
            if PAT.search(cmd):
                print(f"{run.get('created_at')} {id2name.get(run.get('agent_id'))} :: {cmd[:260]!r}")
