"""Continue unused benign trial slots without changing the stopped study."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run as original
import provider
from inspect_ai.log import read_eval_log

BENIGN = original.CELLS[:3]


def registered_plan(root, parent):
    parent_plan = json.loads((parent / "registration.json").read_text())
    original.verify_source(parent)
    for name, digest in parent_plan["runner_sha256"].items():
        assert original.digest(Path(original.__file__).parent / name) == digest, name
    historical = {}
    for path in sorted((parent / "evals").rglob("*.eval")):
        log = read_eval_log(str(path))
        for sample in log.samples or []:
            scope = sample.metadata.get("direct_scope", "")
            parts = scope.split("/")
            if len(parts) != 3 or parts[0] not in {cell[0] for cell in BENIGN}:
                continue
            assert sample.error is None and sample.scores, scope
            key = "/".join(parts[:2])
            ordinal = int(parts[2].split("-")[-1])
            historical.setdefault(key, []).append(ordinal)
    entries = []
    for condition, module, params in BENIGN:
        matching = next(c for c in parent_plan["cells"] if c["condition"] == condition)
        task = original.upstream(parent, module, params)
        assert hashlib.sha256(task.dataset[0].input.encode()).hexdigest() == matching["assignment_sha256"]
        for model in original.MODELS:
            key = condition + "/" + model
            assert sorted(historical[key]) == list(range(1, 9)), key
            entries.append({"condition": condition, "module": module, "model": model,
                            "parameters": params, "carried_slots": list(range(1, 9)),
                            "new_slots": list(range(9, 65)),
                            "assignment_sha256": matching["assignment_sha256"],
                            "time_limit": task.time_limit, "turn_limit": task.turn_limit})
    return {
        "registered_at": original.now(), "parent_output": str(parent),
        "parent_registration_sha256": original.digest(parent / "registration.json"),
        "source_commit": parent_plan["source_commit"], "cells": entries,
        "new_attempts_planned": 336, "historical_scored_carried": 48,
        "target_total_for_six_benign_cells": 384, "full_study_target": 640,
        "scope": "Only original Step 1 and Step 2 bank/none on Luna and Sol; no Step 3/4 calls here.",
        "unchanged": "Original tasks, personas, seeds, tools, turn/time limits, models, route and Sol judge.",
        "scheduling_change": "One epoch per model in each pair, rotating conditions, so an errored cell can be isolated without cancelling independent work.",
        "error_policy": "A returned refusal is retained as an outcome. A provider/infrastructure error holds only the affected model-condition; no retry, model substitution or prompt rewrite.",
        "remaining_cyber_cells": "Held separately; Sol's known provider safety block is not retried or routed through another model.",
        "runner_sha256": original.digest(__file__),
        "original_runner_sha256": parent_plan["runner_sha256"],
    }


def prepare(root, parent):
    assert not (root / "started.json").exists(), "Continuation already started"
    if (parent / "controller.pid").exists():
        try:
            os.kill(int((parent / "controller.pid").read_text()), 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError("Parent collector is still running")
    root.mkdir(parents=True, exist_ok=True)
    if not (root / "source").exists():
        (root / "source").symlink_to(parent / "source", target_is_directory=True)
    assert (root / "source").resolve() == (parent / "source").resolve()
    manifest = root / "upstream-source-manifest.json"
    if not manifest.exists():
        shutil.copyfile(parent / "upstream-source-manifest.json", manifest)
    plan = registered_plan(root, parent)
    destination = root / "registration.json"
    if destination.exists():
        old = json.loads(destination.read_text())
        assert {k: v for k, v in old.items() if k != "registered_at"} == {
            k: v for k, v in plan.items() if k != "registered_at"}, "Registration changed"
    else:
        provider.save(destination, plan)
    return plan


def progress(root, rows, held):
    grouped = {}
    for condition, _, _ in BENIGN:
        for model in original.MODELS:
            key = condition + "/" + model
            selected = [r for r in rows if r["key"] == key]
            grouped[key] = {"historical_scored": 8,
                            "new_attempted": len(selected),
                            "new_scored": sum(r["scored"] for r in selected),
                            "total_scored": 8 + sum(r["scored"] for r in selected),
                            "target": 64, "held": held.get(key)}
    provider.save(root / "progress.json", {
        "updated": original.now(), "historical_scored": 48, "new_attempted": len(rows),
        "new_scored": sum(r["scored"] for r in rows),
        "total_scored_for_benign_cells": 48 + sum(r["scored"] for r in rows),
        "new_attempts_planned": 336, "target_for_benign_cells": 384,
        "per_cell": grouped, "held_cells": held, "full_640_complete": False})


async def collect(root, parent):
    plan = prepare(root, parent)
    for model in original.MODELS:
        check = json.loads((root / "preflight" / (model + ".json")).read_text())
        assert check["passed"] and check["actual_model"] == model
    assert json.loads((root / "preflight/docker.json").read_text())["passed"]
    provider.save(root / "started.json", {"time": original.now(), "pid": os.getpid(),
                                         "new_attempts_planned": 336, "parent": str(parent)})
    provider.event("collection_started", scheduled=336, carried=48, scope="benign_continuation")
    rows, held = [], {}
    progress(root, rows, held)
    try:
        for ordinal in range(9, 65):
            for condition, module, params in BENIGN:
                original.verify_source(root)
                tasks = []
                for model in original.MODELS:
                    key = condition + "/" + model
                    if key in held:
                        continue
                    task = original.upstream(root, module, params)
                    task.epochs = 1
                    task = original.instrument(task, root, condition, model, ordinal - 1)
                    task._name += f"_trial{ordinal:03d}"
                    tasks.append(task)
                if not tasks:
                    continue
                logs = await original.execute(tasks, root / "evals" / f"trial-{ordinal:03d}" / condition)
                for log in logs:
                    model = log.eval.model.split("/", 1)[-1]
                    key = condition + "/" + model
                    samples = log.samples or []
                    assert len(samples) == 1, "Expected one preserved trial per log"
                    sample = samples[0]
                    scope = sample.metadata["direct_scope"]
                    assert scope == f"{key}/epoch-{ordinal:03d}"
                    scores = sample.scores or {}
                    scored = sample.error is None and bool(scores)
                    row = {"key": key, "ordinal": ordinal, "scope": scope,
                           "log": log.location, "scored": scored,
                           "error": sample.error.model_dump(mode="json") if sample.error else None,
                           "scores": {k: v.model_dump(mode="json") for k, v in scores.items()}}
                    rows.append(row)
                    if sample.error or log.status != "success":
                        held[key] = {"ordinal": ordinal,
                                     "reason": (sample.error.message if sample.error else log.status),
                                     "evidence": str(root / "requests" / scope)}
                        provider.event("cell_held", key=key, **held[key])
                    progress(root, rows, held)
                    provider.save(root / "trial-index.json", rows)
                    provider.event("trial_recorded", scope=scope, model=model, scored=scored,
                                   error=sample.error.message if sample.error else None)
        provider.save(root / "completion.json", {"time": original.now(),
            "status": "benign_subset_complete" if not held else "benign_subset_partial",
            "new_attempted": len(rows), "new_scored": sum(r["scored"] for r in rows),
            "historical_scored": 48, "held_cells": held, "full_640_complete": False})
        provider.event("collection_completed", scope="benign_continuation", attempted=len(rows), held=held)
    except BaseException as error:
        provider.save(root / "collector-failure.json", {"time": original.now(),
            "type": type(error).__name__, "message": str(error), "recorded_trials": len(rows)})
        provider.event("collection_stopped", type=type(error).__name__, message=str(error))
        raise


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    root, parent = args.output.resolve(), args.parent.resolve()
    os.environ["SWH_LW_OUTPUT"] = str(root)
    os.environ["INSPECT_DISPLAY"] = "plain"
    if args.prepare:
        plan = prepare(root, parent)
        print("Registered 336 unused benign trial slots, carrying 48 completed trials; no repeated slots.")
    else:
        await collect(root, parent)


if __name__ == "__main__":
    asyncio.run(main())
