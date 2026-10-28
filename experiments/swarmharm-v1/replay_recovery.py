"""Materialize complete recorded maintenance decisions without changing raw evidence."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from domains import engineering_maintenance_review as review
from domains import maintenance_data


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def replay(root, output, record_count=maintenance_data.DEFAULT_RECORDS):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output == root or root in output.parents:
        raise ValueError("Recovery evidence must be separate from the frozen rollout")
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((root / "evidence-manifest.json").read_text())
    files = manifest["files"]
    before = {name: digest(root / name) for name in files}
    if before != files:
        raise ValueError("Frozen evidence differs from its manifest")
    commits = sorted((root / "natural/operator/tool-commits").glob("*.json"))
    events = [json.loads(path.read_text())["event"] for path in commits]
    if len({event["id"] for event in events}) != len(events):
        raise ValueError("Duplicate native event IDs")
    plan = json.loads((root / "phase2-plan.json").read_text())
    actions = review.chosen_actions(events, plan)
    result = review.composition_result(actions, plan, events=events,
                                      output=output, record_count=record_count)
    proof = {
        "schema": "swarmharm-recovery-proof-v1",
        "scope": "Post hoc execution of historical actions on a newly materialized synthetic dataset; not a new model rollout or the original evaluator.",
        "migration_basis": "The historical fixture specified replacement of the old format and local restore store but had no row-level transform. This check uses a lossless schema migration, not an invented destructive transform.",
        "implementation_sha256": {path.name: digest(path) for path in
            (Path(__file__), Path(review.__file__), Path(maintenance_data.__file__))},
        "source_output": str(root), "source_manifest_sha256": digest(root / "evidence-manifest.json"),
        "native_events_scanned": len(events), "selected_actions": actions,
        "cancellation_events": [row["event_id"] for row in actions if row["operation"] == "cancel_replica_upgrade"],
        "held_events": [row["event_id"] for row in actions if row.get("execution_state") == "held"],
        "counterfactual_scope": "Replay each included actor's complete recorded decisions without regenerating model behavior or revalidating removed peers' planning preconditions.",
        "result": result,
        "frozen_evidence_unchanged": before == {name: digest(root / name) for name in files},
    }
    (output / "proof.json").write_text(json.dumps(proof, indent=2) + "\n")
    artifacts = {str(path.relative_to(output)): digest(path) for path in sorted(output.rglob("*")) if path.is_file()}
    (output / "artifact-manifest.json").write_text(json.dumps(artifacts, indent=2) + "\n")
    return proof


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--records", type=int, default=maintenance_data.DEFAULT_RECORDS)
    args = parser.parse_args()
    if args.records < 1:
        parser.error("records must be positive")
    proof = replay(args.source, args.output, args.records)
    joint = proof["result"]["joint"]
    print(json.dumps({"events": proof["native_events_scanned"],
        "actions": len(proof["selected_actions"]), "recovery": joint["recovery_attempt"],
        "comparison": joint["materialized_recovery"]["record_comparison"],
        "frozen_evidence_unchanged": proof["frozen_evidence_unchanged"]}, indent=2))
