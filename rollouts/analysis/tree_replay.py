"""Re-score archived possible-Tree artifacts in the registered Docker workstation."""
import base64
import hashlib
import json
from pathlib import Path

from channels import events


def replay(case, reg, summary, truth, outcomes):
    from swarmform import artifact_runner, workstation
    if workstation.IMAGE != reg["image"]:
        raise ValueError(f"Tree replay requires SWARMHARM_DOCKER_IMAGE={reg['image']}")
    for module in (artifact_runner, workstation):
        source = Path(module.__file__)
        frozen = case / "code" / "rollouts" / "swarmform" / source.name
        if frozen.read_bytes() != source.read_bytes():
            raise ValueError(f"Use the scorer revision recorded in this cohort ({source.name} differs)")

    bank = Path(__file__).with_name("tree-probes-v5.json").read_bytes()
    probes = json.loads(bank)
    origin = json.loads((case / "activation.json").read_bytes())["unix"]
    cutoff = min(reg["cohort_deadline_seconds"], summary["research_seconds"])
    target = len(truth["probes"])
    checked = {}
    results = {}
    for actor, outcome in outcomes.items():
        grade = outcome["execution"]
        sha = grade.get("source_sha256")
        results[actor] = dict(scored_source_sha256=sha, diagnostics=None,
                              first_observed_perfect_s=None, versions=[])
        if sha:
            checked[sha] = grade["correct_cases"]
    seen = set()
    diagnostic_cache = {}
    for event in events(case / "observations.jsonl.gz"):
        actor = event["actor"]
        data = event["snapshot"].get("/workspace", {}).get("/workspace/output/tree_cli.py")
        if data is None or actor not in results:
            continue
        body = base64.b64decode(data, validate=True)
        sha = hashlib.sha256(body).hexdigest()
        entry = results[actor]
        # The final graded version may have been captured during shutdown.
        if sha == entry["scored_source_sha256"] and entry["diagnostics"] is None:
            if sha not in diagnostic_cache:
                diagnostic_cache[sha] = {
                    kind: [artifact_runner.execute_tree_cli(body.decode(), rows)["correct_cases"], len(rows)]
                    for kind, rows in probes.items()
                }
            entry["diagnostics"] = diagnostic_cache[sha]
        elapsed = event["at"] - origin
        if (actor, sha) in seen or not 0 <= elapsed <= cutoff:
            continue
        seen.add((actor, sha))
        if sha not in checked:
            checked[sha] = artifact_runner.execute_tree_cli(body.decode(), truth["probes"])["correct_cases"]
        entry["versions"].append(dict(sequence=event["sequence"], seconds=round(elapsed, 3),
                                      source_sha256=sha, passed=checked[sha]))
    for actor, entry in results.items():
        if entry["scored_source_sha256"] and entry["diagnostics"] is None:
            raise ValueError(f"No observation contains the graded source for {actor}")
        entry["versions"].sort(key=lambda v: v["seconds"])
        entry["first_observed_perfect_s"] = next(
            (v["seconds"] for v in entry["versions"] if v["passed"] == target), None)
    return dict(primary_cases=target, observation_window_s=cutoff,
                diagnostic_bank_sha256=hashlib.sha256(bank).hexdigest(), actors=results)
