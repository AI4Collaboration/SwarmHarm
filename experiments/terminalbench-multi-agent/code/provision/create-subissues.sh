#!/bin/bash
# 在本机运行（由父 issue 的 agent 执行）：为 experiments.json 中 stage=experiment 的条目各创建一个子 issue，指派给 Tabbycat。
# 参数：PARENT_ISSUE_ID [STATUS，默认 todo] [STAGE，默认 1]
set -euo pipefail
# env.sh 把实验用的 multica 0.6.1 放在 PATH 最前面；子 issue 创建在主 Multica 上，使用原来的 CLI
MULTICA_MAIN=$(command -v multica)
source "$(dirname "$0")/env.sh"
PARENT=$1; STATUS=${2:-todo}; STAGE=${3:-1}
python3 - "$BUNDLE_DIR" > "$BUNDLE_DIR/.scratch/subissues.tsv" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
exps = json.loads((root / "experiments.json").read_text())
tasks = json.loads((root / "tasks.json").read_text())
tmpl = (root / "prompts" / "subissue-template.md").read_text()
out = root / ".scratch" / "subissues"
out.mkdir(parents=True, exist_ok=True)
harness_name = {"codex": "Codex", "claude": "Claude Code"}
for exp, e in exps.items():
    if e["stage"] != "experiment":
        continue
    t = tasks[e["task"]]
    body = tmpl.format(exp=exp, model=e["model"], harness_name=harness_name[e["harness"]], n=e["n_agents"], label=t["label"], task=e["task"], hours=t["expert_time_hours"])
    (out / f"{exp}.md").write_text(body)
    title = f"SWH-30 experiment {exp}: {e['model']} × {e['n_agents']} agents × {t['label']} {e['task']}"
    print(f"{exp}\t{title}")
PY
while IFS=$'\t' read -r EXP TITLE; do
  "$MULTICA_MAIN" issue create --title "$TITLE" --description-file "$BUNDLE_DIR/.scratch/subissues/$EXP.md" --parent "$PARENT" --assignee Tabbycat --stage "$STAGE" --status "$STATUS" --output json | jq -r '[.identifier,.id] | @tsv' | sed "s/^/$EXP\t/"
done < "$BUNDLE_DIR/.scratch/subissues.tsv"
