#!/usr/bin/env python3
"""Replay an observed request with and without the cache ACL repair. No model calls."""
import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads(path.read_text())


def check(source, destination):
    reg = load(source / "registration.json")
    code = REPO / "experiments/hf-fleet-v2/world.py"
    assert hashlib.sha256(code.read_bytes()).hexdigest() == reg["code_hashes"][str(code.relative_to(REPO))]
    spec = importlib.util.spec_from_file_location("mechanism_world", code)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixtures, references = load(source / "fixtures.json"), load(source / "references.json")
    cell = reg["cells"][0]
    audit = load(source / cell["id"] / "world.json")
    target = next(e for e in audit["events"] if e.get("protected_source_read") and e["accepted"])
    worlds = []
    for opened in (True, False):
        config = deepcopy(audit["fleet_config"])
        config["weakness_open"] = opened
        worlds.append(module.FleetWorld(fixtures, references, world_id=audit["world_id"], **config))
    call_index = 0
    for record in audit["replay_records"]:
        if record["action"] == "add_actor":
            for world in worlds:
                world.add_actor(record["actor"], record["task_id"], record["wave"])
        elif record["action"] == "finish":
            for world in worlds:
                world.finish(record["actor"])
        else:
            call_index += 1
            results = [world.call(record["actor"], record["operation"], **record["arguments"]) for world in worlds]
            if call_index == int(target["event_id"].split("_")[-1]):
                assert module.digest(results[0]) == record["result_sha256"]
                assert results[0]["status"] == 200 and results[1]["status"] == 403
                result = {"model_calls": 0, "source": str(source), "actor": target["actor_id"],
                    "observed_event": target["event_id"], "operation": record["operation"],
                    "arguments": record["arguments"], "prefix_results_identical": True,
                    "open_status": results[0]["status"], "repaired_status": results[1]["status"],
                    "source_world_sha256": hashlib.sha256((source / cell["id"] / "world.json").read_bytes()).hexdigest(),
                    "analysis_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "interpretation": "The ACL repair blocks this same observed request. This is a deterministic service counterfactual, not a model rollout under repaired conditions."}
                destination.write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result))
                return
            assert all(module.digest(value) == record["result_sha256"] for value in results), record
    raise AssertionError("Observed target request was not replayed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.source.resolve(), args.output.resolve())
