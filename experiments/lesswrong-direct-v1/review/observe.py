"""Read-only status and score extraction. Never calls a model or alters a run."""
import argparse
import collections
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from inspect_ai.log import read_eval_log


def observe(root):
    rows = []
    for line in (root / "events.jsonl").read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # Writer may have appended only part of the last line.
    started, exported, pending_calls, failures = {}, set(), {}, []
    for event in rows:
        if event.get("scope", "").startswith("preflight"):
            continue
        kind = event["kind"]
        if kind == "sample_started":
            started[event["scope"]] = event["time"]
        elif kind == "sample_cleanup":
            exported.add(event["scope"])
        elif kind == "request_started":
            pending_calls[event["label"]] = event
        elif kind in ("request_completed", "request_failed"):
            pending_calls.pop(event["label"], None)
            if kind == "request_failed":
                failures.append(event)
    per_cell = collections.defaultdict(lambda: {"started": 0, "exported": 0, "planned": 64})
    for scope in started:
        key = "/".join(scope.split("/")[:2])
        per_cell[key]["started"] += 1
        per_cell[key]["exported"] += int(scope in exported)
    log_scores, incomplete_logs = [], []
    for path in sorted((root / "evals").rglob("*.eval")):
        try:
            log = read_eval_log(str(path))
        except Exception as error:
            incomplete_logs.append({"path": str(path), "type": type(error).__name__})
            continue
        for sample in log.samples or []:
            log_scores.append({
                "task": log.eval.task, "model": log.eval.model,
                "epoch": sample.epoch, "id": sample.id,
                "log": str(path), "log_status": log.status,
                "error": sample.error.model_dump(mode="json") if sample.error else None,
                "limit": sample.limit.model_dump(mode="json") if sample.limit else None,
                "scores": {name: value.model_dump(mode="json")
                           for name, value in (sample.scores or {}).items()},
                "final": sample.output.completion if sample.output else None,
            })
    alive = False
    if (root / "controller.pid").exists():
        try:
            os.kill(int((root / "controller.pid").read_text()), 0)
            alive = True
        except ProcessLookupError:
            pass
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "process_alive": alive, "completion_present": (root / "completion.json").exists(),
        "collector_failure": json.loads((root / "collector-failure.json").read_text())
            if (root / "collector-failure.json").exists() else None,
        "planned": 640, "started": len(started), "exported": len(exported),
        "per_cell": dict(per_cell), "active_samples": sorted(set(started) - exported),
        "pending_requests": list(pending_calls.values()), "provider_failures": failures,
        "last_event": {k: v for k, v in rows[-1].items() if k != "usage"} if rows else None,
        "scored_samples": log_scores, "currently_unreadable_logs": incomplete_logs,
        "interpretation": "Stage-specific scores use the substituted Sol judge. Communication is not itself misalignment. Exported traces can include failures; only completion.json confirms the planned collection completed.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--save", type=Path)
    args = parser.parse_args()
    report = observe(args.output.resolve())
    if args.save:
        args.save.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    compact = {k: v for k, v in report.items()
               if k not in {"scored_samples", "pending_requests", "provider_failures"}}
    compact["pending_requests"] = len(report["pending_requests"])
    compact["provider_failures"] = len(report["provider_failures"])
    compact["scores_available"] = len(report["scored_samples"])
    print(json.dumps(compact, indent=2, ensure_ascii=False))
