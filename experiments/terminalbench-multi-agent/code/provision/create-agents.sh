#!/bin/bash
# 在本机运行：在实验 Multica 上创建 N 个 agent（Dev A..）、Dev Team squad，并记录 agents.json。参数：EXP
set -euo pipefail
source "$(dirname "$0")/env.sh"
EXP=$1; D=$(exp_dir "$EXP")
N=$(exp_field "$EXP" n_agents); HARNESS=$(exp_field "$EXP" harness); MODEL=$(exp_field "$EXP" model)
M="$BUNDLE_DIR/provision/m30.sh"
"$M" "$EXP" runtime list --output json > "$D/runtimes.json"
python3 - "$D" "$EXP" "$N" "$HARNESS" <<'PY'
import json, sys
d, exp, n, harness = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
rows = json.load(open(f"{d}/runtimes.json"))
rows = rows if isinstance(rows, list) else rows.get("runtimes", rows.get("items", []))
out = {}
for i in range(1, n + 1):
    device = f"swh30-{exp}-rt-{chr(96 + i)}"
    # runtime list 的 device_info 形如 "<device-name> · <harness 版本>"，provider 为 codex 或 claude
    match = [r for r in rows if (r.get("device_info") or "").split(" · ")[0] == device and r.get("provider") == harness]
    assert len(match) == 1, (device, harness, [(r.get("device_info"), r.get("provider")) for r in rows])
    out[f"Dev {chr(64 + i)}"] = {"runtime_id": match[0]["id"], "device": device}
json.dump(out, open(f"{d}/runtime-map.json", "w"), indent=1)
print(json.dumps(out, indent=1))
PY
declare -A AGENT_IDS
for i in $(seq 1 "$N"); do
  NAME="Dev $(printf "\\$(printf '%03o' $((64 + i)))")"
  RID=$(python3 -c "import json;print(json.load(open('$D/runtime-map.json'))['$NAME']['runtime_id'])")
  EXISTING=$("$M" "$EXP" agent list --output json | python3 -c "import json,sys; rows=json.load(sys.stdin); rows=rows if isinstance(rows,list) else rows.get('agents',[]); print(next((a['id'] for a in rows if a['name']=='$NAME'),''))")
  if [ -z "$EXISTING" ]; then
    EXISTING=$("$M" "$EXP" agent create --name "$NAME" --runtime-id "$RID" --model "$MODEL" --thinking-level max --max-concurrent-tasks 1 --public-to-workspace --output json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
  fi
  AGENT_IDS["$NAME"]=$EXISTING
done
SQUAD=$("$M" "$EXP" squad list --output json | python3 -c "import json,sys; rows=json.load(sys.stdin); rows=rows if isinstance(rows,list) else rows.get('squads',[]); print(next((s['id'] for s in rows if s['name']=='Dev Team'),''))")
if [ -z "$SQUAD" ]; then
  SQUAD=$("$M" "$EXP" squad create --name "Dev Team" --leader "${AGENT_IDS["Dev A"]}" --output json | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
  for i in $(seq 2 "$N"); do
    NAME="Dev $(printf "\\$(printf '%03o' $((64 + i)))")"
    "$M" "$EXP" squad member add "$SQUAD" --member-id "${AGENT_IDS["$NAME"]}" --type agent --role member --output json >/dev/null
  done
fi
python3 - "$D" "$SQUAD" "${!AGENT_IDS[@]}" <<PY
import json, sys
d, squad = sys.argv[1], sys.argv[2]
ids = {$(for k in "${!AGENT_IDS[@]}"; do printf '"%s":"%s",' "$k" "${AGENT_IDS[$k]}"; done)}
m = json.load(open(f"{d}/runtime-map.json"))
for k, v in ids.items(): m[k]["agent_id"] = v
json.dump({"squad_id": squad, "agents": m}, open(f"{d}/agents.json", "w"), indent=1)
print(json.dumps({"squad_id": squad, "agents": m}, indent=1))
PY
