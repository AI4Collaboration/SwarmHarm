"""Read-only extraction of Step 2 reach-out evidence from completed Inspect logs."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from inspect_ai.log import read_eval_log


def interval(successes, total, z=1.959963984540054):
    if not total:
        return [0.0, 1.0]
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def review(root):
    if not (root / "completion.json").exists():
        raise RuntimeError("The registered 128-trial collection is not complete")
    rows = []
    for path in sorted((root / "evals").rglob("*.eval")):
        log = read_eval_log(str(path))
        for sample in log.samples or []:
            if sample.error:
                raise RuntimeError(f"Sample error in {path}: {sample.error.message}")
            scope = sample.metadata["direct_scope"]
            condition = scope.split("/", 1)[0]
            ask = sample.scores["reachout_ask_scorer"].model_dump(mode="json")
            broad = sample.scores["reachout_broad_scorer"].model_dump(mode="json")
            ask_meta = ask.get("metadata", {})
            broad_meta = broad.get("metadata", {})
            rows.append({
                "condition": condition,
                "scope": scope,
                "log": str(path),
                "strict_ask": bool(ask_meta.get("ask_signature")),
                "broad_reachout": bool(broad_meta.get("broad_signature")),
                "ask_level": ask_meta.get("ask_level"),
                "headline": ask.get("answer"),
                "explanation": ask.get("explanation"),
                "registry_put_paths": ask_meta.get("registry_put_paths", []),
                "put_bodies": ask_meta.get("put_bodies", {}),
                "final": sample.output.completion if sample.output else None,
            })
    expected = {"protein_bank": 64, "protein_none": 64}
    summary = {}
    for condition, target in expected.items():
        selected = [row for row in rows if row["condition"] == condition]
        if len(selected) != target:
            raise RuntimeError(f"{condition} has {len(selected)} samples; expected {target}")
        asks = sum(row["strict_ask"] for row in selected)
        broad = sum(row["broad_reachout"] for row in selected)
        summary[condition] = {
            "n": len(selected),
            "strict_asks": asks,
            "strict_ask_rate": asks / len(selected),
            "strict_ask_wilson_95": interval(asks, len(selected)),
            "broad_reachouts": broad,
            "broad_reachout_rate": broad / len(selected),
            "broad_reachout_wilson_95": interval(broad, len(selected)),
        }
    result = {
        "passed_structural_checks": True,
        "samples": len(rows),
        "summary": summary,
        "strict_candidates": [row for row in rows if row["strict_ask"]],
        "all_trials": rows,
        "interpretation": (
            "This reproduces or fails to reproduce the public Step 2 reach-out effect only. "
            "A peer-directed request is communication, not evidence of misalignment or harm. "
            "The original rubric is retained, but GPT-5.6 Sol replaces the paper's Opus judge; "
            "every positive candidate therefore requires human inspection of the stored request body."
        ),
    }
    destination = root / "independent-review.json"
    if destination.exists():
        raise RuntimeError("Review already exists; do not replace it")
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review(args.output.resolve())
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
