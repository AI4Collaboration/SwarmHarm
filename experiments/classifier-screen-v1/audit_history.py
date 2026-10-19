"""Read-only review of saved response/error records; no inference calls."""
from collections import Counter
import json
from pathlib import Path
import sys

from build import REPO, save
from run import classify, digest


def audit(root):
    packets = json.loads((root / "packets.json").read_text())
    input_ids = {p["id"] for p in packets}
    records, counts, read_errors = [], Counter(), []
    directories = [REPO / "experiments"]
    readiness = REPO.parent / "eval-readiness"
    prefixes = ("hf-", "sol-", "luna-", "astra-", "wayfinding-", "model-coverage-", "lesswrong-direct-")
    directories.extend(p for p in readiness.iterdir() if p.is_dir() and p.name.startswith(prefixes))
    for directory in directories:
        for suffix in ("*.error.json", "*.response.json"):
            for path in directory.rglob(suffix):
                parts = path.relative_to(directory).parts
                if any(p in {"source", "code", ".venv", "node_modules", "preflight", "diagnostic", "comprehension"} for p in parts):
                    continue
                is_error = path.name.endswith(".error.json")
                request = path.with_name(path.name.replace(".error.json" if is_error else ".response.json", ".request.json"))
                if not request.exists():
                    continue
                try:
                    body = json.loads(request.read_text())
                    if not body.get("tools"):
                        continue  # Separate judges/retrospectives are not task-worker refusals.
                    value = json.loads(path.read_text())
                    outcome = classify(value, is_error)
                    counts[outcome["status"]] += 1
                    if outcome["status"] not in {"provider_filter", "native_refusal", "text_refusal_candidate"}:
                        continue
                    key = digest({k: body[k] for k in ("instructions", "input", "tools") if k in body})
                    records.append({"model": body.get("model"), "request": str(request),
                        "outcome": str(path), "exact_current_initial_input": key in input_ids, **outcome})
                except (OSError, ValueError) as error:
                    read_errors.append({"path": str(path), "type": type(error).__name__})
    save(root / "historical-refusal-review.json", {"scope": "Saved task-worker response/error records; archived source copies, preflights and separate judges excluded. Historical inputs are not relabeled as current prompts.",
        "record_counts_not_trial_counts": counts, "candidates": records, "read_errors": read_errors})
    print(json.dumps({"historical_record_counts": counts, "review_candidates": len(records), "read_errors": len(read_errors)}))


if __name__ == "__main__":
    audit(Path(sys.argv[1]))
