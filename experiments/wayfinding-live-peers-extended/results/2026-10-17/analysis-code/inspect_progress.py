"""Read exported operator artifacts only; never contact or prompt subjects."""
from pathlib import Path
import json

root = Path(__file__).parent / "model-run-01"
reg = json.loads((root / "registration.json").read_text())
state = root / "operator-progress-observed.json"
seen = json.loads(state.read_text()) if state.exists() else {}
for cell in reg["independent_worlds"]:
    folder = root / cell["id"]
    if not (folder / "world.json").exists():
        print(json.dumps({"world": cell["id"], "status": "not yet exported"}))
        continue
    try:
        world = json.loads((folder / "world.json").read_text())
    except json.JSONDecodeError:
        print(json.dumps({"world": cell["id"], "status": "export being written"}))
        continue
    events = world["events"]
    actors = []
    for name in cell["actor_order"]:
        p = folder / name / "result.json"
        if not p.exists():
            continue
        try:
            actor = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        recent = [e for e in events if e["actor"] == name]
        actors.append({**{k: actor[k] for k in ("id", "status", "steps", "tools")},
                       "progress": world["progress"][name],
                       "last_operation": recent[-1]["operation"] if recent else None})
    writes = [e for e in events if e["operation"] == "cache_put" and e["accepted"] and e.get("scope") == "shared"]
    reads = [e for e in events if e["operation"] == "cache_get" and e["accepted"] and e.get("origin_kind") == "model_text" and e.get("origin_actor") != e["actor"]]
    print(json.dumps({"world": cell["id"], "requests": world["model_request_attempts"], "actors": actors,
                      "shared_writes": len(writes), "peer_text_reads": len(reads), "waits": len(world["waits"])}))
    for e in writes:
        if e["step"] > seen.get(cell["id"], 0):
            print(json.dumps({"new_shared_write": e["id"], "actor": e["actor"], "key": e["target"], "text": e["text"][:2400]}))
    seen[cell["id"]] = len(events)
state.write_text(json.dumps(seen, indent=2))
