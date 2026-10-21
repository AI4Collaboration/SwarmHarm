"""Register source-exact recovery baselines; retain earlier preparation errors."""
import ast
import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import httpx

from build import REPO, load_module, save
from run import MODELS, digest, now, request


def prepare(parent):
    source = REPO / "experiments/hf-safety-pilot"
    m = load_module(source / "run.py", "recovery_source")
    screening_module = sys.modules["run"]
    sys.modules["run"] = m
    try:
        relational = load_module(source / "run_relational.py", "relational_source")
        neutral = load_module(source / "run_unscaffolded.py", "unscaffolded_source")
    finally:
        sys.modules["run"] = screening_module
    bodies = []
    def add(entry, variant, prompt, tools):
        body = {"instructions": "Complete the user's task.", "input": [{"role": "user", "content": prompt}], "tools": tools}
        bodies.append({"id": digest(body), "body": body, "aliases": [{"family": "hf-safety-pilot", "task": "inventory-recovery", "variant": {"entry": entry, **variant}}]})
    add("run_relational", {"feasible": True, "job": "job-a"},
        m.task_prompt("job-a", "job-b", feasible=True) + "\n" + relational.BASELINE_INPUT_NOTE, m.TOOLS)
    add("run_unscaffolded", {"feasible": True, "job": "job-a"},
        neutral.assigned_prompt("job-a", "neutral", feasible=True) + "\n" + neutral.BASELINE_INPUT_NOTE,
        neutral.tools_for("neutral"))
    tree = ast.parse((source / "run.py").read_text())
    run_world = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_world")
    notice = next(ast.literal_eval(node.value) for node in ast.walk(run_world)
                  if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == "prompt")
    for job, peer in (("job-a", "job-b"), ("job-b", "job-a")):
        add("run.py", {"notice_level": "none/reversible/irreversible", "job": job},
            m.task_prompt(job, peer) + notice, m.TOOLS)
    original = json.loads((parent / "packets.json").read_text())
    invalid = [p["id"] for p in original if any(a["family"] == "hf-safety-pilot" and
        a["variant"].get("entry") in {"run_relational", "run_unscaffolded"} and
        a["variant"].get("feasible") for a in p["aliases"])]
    assert len(invalid) == 4
    root = parent / "input-correction"
    save(root / "packets.json", bodies)
    save(root / "registration.json", {"registered_at": now(), "models": MODELS, "inputs": len(bodies),
        "excluded_primary_input_ids": invalid,
        "reason": "Four first-pass prepared feasible inputs did not match the actual recovery baseline assembly. They remain in raw evidence but are excluded from source-exact task coverage. Add the two actual job-a baselines and the existing lifecycle-notice entry-point inputs. No blocked request is rewritten or reissued.",
        "model_settings": "Same high reasoning, one request/model, timeout 300s; no tools, retries or fallback.",
        "packets_sha256": digest(bodies),
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("run*.py")}})
    return root


async def collect(root):
    parent = root.parent
    assert (parent / "completion.json").exists(), "Do not overlap screening requests"
    assert not (root / "started.json").exists(), "No repeat or replacement"
    save(root / "started.json", {"time": now()})
    packets = json.loads((root / "packets.json").read_text())
    rows = []
    async def run_model(model):
        async with httpx.AsyncClient(timeout=300) as client:
            for packet in packets:
                folder = root / "requests" / model / packet["id"]
                outcome = await request(packet, model, folder, client)
                row = {"time": now(), "model": model, "input_id": packet["id"], "aliases": packet["aliases"], **outcome, "evidence": str(folder)}
                rows.append(row)
                with (root / "outcomes.jsonl").open("a") as stream:
                    stream.write(json.dumps(row) + "\n")
                print(json.dumps({"model": model, "status": row["status"], "entry": packet["aliases"][0]["variant"]}), flush=True)
                if outcome["status"] != "initial_accepted":
                    break
    await asyncio.gather(*(run_model(m) for m in MODELS))
    save(root / "completion.json", {"time": now(), "rows": len(rows), "statuses": [r["status"] for r in rows]})


if __name__ == "__main__":
    root = Path(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2] == "--collect":
        asyncio.run(collect(root / "input-correction"))
    else:
        print(prepare(root))
