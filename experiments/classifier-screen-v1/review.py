"""Export confirmed holds and review candidates without changing study evidence."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from build import REPO, save


def review(root):
    packets = {p["id"]: p for p in json.loads((root / "packets.json").read_text())}
    rows = [json.loads(line) for line in (root / "outcomes.jsonl").read_text().splitlines()]
    by_task = defaultdict(list)
    for row in rows:
        if row["status"] in {"provider_filter", "native_refusal", "text_refusal_candidate"}:
            for alias in row["aliases"]:
                by_task[(alias["family"], alias["task"])].append(row)
    destination = REPO / "data/task-quarantine/2026-10-19"
    entries = []
    for (family, task), outcomes in sorted(by_task.items()):
        confirmed = any(r["status"] in {"provider_filter", "native_refusal"} for r in outcomes)
        evidence = destination / family / task
        input_ids = sorted({r["input_id"] for r in outcomes})
        for key in input_ids:
            save(evidence / (key + ".original-input.json"), packets[key]["body"])
        entries.append({"family": family, "task": task,
            "status": "quarantined_pending_removal" if confirmed else "held_for_text_review",
            "reason": sorted({r["status"] for r in outcomes}),
            "observed_models": sorted({r["model"] for r in outcomes}),
            "scope": "Task held for new admission across both screen models; this is not a claim that both models refused.",
            "original_input_ids": input_ids, "evidence": outcomes,
            "snapshots": str(evidence.relative_to(REPO)),
            "original_source_deleted": False, "prompts_rewritten": False})
    manifest = {"updated": datetime.now(timezone.utc).isoformat(), "screen_output": str(root),
        "initial_screen_only": True, "entries": entries,
        "rule": "Exclude quarantined tasks from new study admission. Preserve all original source and historical results. Text matches require context review; no automatic deletion or bypass rewrite."}
    save(destination / "manifest.json", manifest)
    save(REPO / "data/task-quarantine/active.json", {"manifest": "2026-10-19/manifest.json",
        "held_tasks": [{k: e[k] for k in ("family", "task", "status")} for e in entries]})
    eligible = [p["id"] for p in packets.values() if not any(
        (a["family"], a["task"]) in by_task for a in p["aliases"])]
    save(root / "not-quarantined-inputs.json", {"input_ids": eligible,
        "meaning": "Not selected for quarantine by observed screening evidence. This is not full-trajectory clearance or permission to restart a study."})
    family_rows = {}
    for row in rows:
        for family in {a["family"] for a in row["aliases"]}:
            family_rows.setdefault(family, {}).setdefault(row["model"], Counter())[row["status"]] += 1
    save(root / "coverage.json", {"per_family_model": family_rows, "statuses": Counter(r["status"] for r in rows),
        "quarantined_tasks": len([e for e in entries if e["status"] == "quarantined_pending_removal"]),
        "text_review_tasks": len([e for e in entries if e["status"] == "held_for_text_review"]),
        "completion_present": (root / "completion.json").exists()})
    print(json.dumps({"screen_rows": len(rows), "quarantined_tasks": len(entries),
                      "statuses": Counter(r["status"] for r in rows)}))


if __name__ == "__main__":
    review(Path(sys.argv[1]))
