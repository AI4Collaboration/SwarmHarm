"""Describe observed continuation beyond the old cap without a causal claim."""
import argparse
from collections import Counter
import json
from pathlib import Path


def read(p):
    return json.loads(p.read_text())


def main(root):
    reg = read(root / "registration.json")
    worlds = []
    for cell in reg["independent_worlds"]:
        folder = root / cell["id"]
        if not (folder / "results.json").exists():
            continue
        results = read(folder / "results.json")
        assert all(r["status"] not in {"running", "waiting"} for r in results)
        world = read(folder / "world.json")
        starts = [s for s in read(folder / "scheduler.json") if s["event"] == "response_start"]
        by_event = {}
        for i, s in enumerate(starts):
            end = starts[i + 1]["after_event"] if i + 1 < len(starts) else len(world["events"])
            for e in world["events"][s["after_event"]:end]:
                assert e["actor"] == s["actor"]
                by_event[e["id"]] = {"actor_response": s["response"], "active_actors": s["active_actors"],
                                     "elapsed_seconds": s["elapsed_seconds"]}
        assert len(by_event) == len(world["events"])
        actors = []
        for r in results:
            post = Counter()
            for p in (folder / r["id"] / "trace").glob("*-tool-*.json"):
                if int(p.name.split("-")[0]) > 32:
                    post[read(p)["name"]] += 1
            actors.append({"actor": r["id"], "status": r["status"], "responses": r["steps"],
                           "responses_after_32": max(0, r["steps"] - 32), "tools_after_32": dict(post),
                           "stages_submitted": world["progress"][r["id"]]})
        late = []
        for e in world["events"]:
            s = by_event[e["id"]]
            if s["actor_response"] > 32 and (e["operation"] == "submit_stage" or
                    (e["operation"] == "cache_put" and e.get("scope") == "shared" and e["accepted"])):
                late.append({"event": e["id"], "actor": e["actor"], "operation": e["operation"],
                             "target": e["target"], **s})
        worlds.append({"id": cell["id"], "actors": actors, "late_submissions_and_shared_writes": late,
                       "elapsed_seconds": read(folder / "cleanup.json")["elapsed_seconds"]})
    result = {"basis": "Complete recorded scheduler, actor results and exact tool traces; descriptive within these trajectories",
              "old_response_cap": 32, "current_response_cap": reg["max_responses_per_actor"], "worlds": worlds,
              "actors_exceeding_old_cap": sum(a["responses"] > 32 for w in worlds for a in w["actors"]),
              "actors_finishing_after_old_cap": sum(a["responses"] > 32 and a["status"] == "completed" for w in worlds for a in w["actors"]),
              "no_randomized_budget_effect_estimate": True,
              "completion_not_equivalent_to_correctness_or_stable_cooperation": True}
    (root / "budget-continuation-review.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    main(p.parse_args().output)
