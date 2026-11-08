#!/usr/bin/env python3
"""Create versioned current-source claim monitors without changing raw evidence."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "experiments/swarmharm-v1"))
sys.path.insert(0, str(REPO / "experiments/runtime"))
from phase2 import claim_evidence, communication_evidence, delivery_notes, delivery_receipts, work_files
import guardrails


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Refusing to replace {path}")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    root = guardrails.outside_repository(args.output, REPO, "Rollout output")
    review_root = guardrails.outside_repository(
        args.review_dir, REPO, "Monitor review"
    )
    if review_root.exists():
        parser.error(f"review directory already exists: {review_root}")
    registration = json.loads((root / "registration.json").read_text())
    review = json.loads((root / "independent-review.json").read_text())
    world = json.loads((root / "natural/world.json").read_text())
    actors = registration["plan"]["natural"]
    for actor in actors:
        # The exporter validates an existing trajectory in place and only creates missing ones.
        original = root / "natural" / actor / "agent/trajectory.json"
        if not original.is_file():
            raise FileNotFoundError(f"Archived ATIF is required for read-only reassessment: {original}")
    assignments = registration["phase2"]["assignments"]
    format_name = registration['phase2'].get('configuration', {}).get(
        'sharing', {}).get('communication_format', 'reporting_notes')
    carrier = work_files if format_name == 'work_files' else delivery_notes
    observations = carrier.audit(world["events"], assignments)
    observations["service_receipts"] = delivery_receipts.audit(world["events"], assignments)
    communication = communication_evidence.build(root, world, observations, actors)
    integrated = {"collective_outcomes": review["outcomes"]["collective_outcomes"]}
    action = claim_evidence.action_monitor(root, registration, integrated)
    packet = claim_evidence.transcript_packet(root, registration, communication)
    write_new(review_root / "communication-evidence.json", communication)
    write_new(review_root / "action-monitor.json", action)
    write_new(review_root / "transcript-judge-input.json", packet)
    write_new(review_root / "provenance.json", {
        "source_output": str(root),
        "source_registration_sha256": claim_evidence.digest_file(
            root / "registration.json"
        ),
        "source_independent_review_sha256": claim_evidence.digest_file(
            root / "independent-review.json"
        ),
        "monitor_source_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, check=True,
            capture_output=True, text=True,
        ).stdout.strip(),
        "action_monitor_schema": claim_evidence.ACTION_SCHEMA,
        "transcript_packet_schema": claim_evidence.PACKET_SCHEMA,
    })
    print(json.dumps({
        "registered_claim": action["registered_claim"],
        "mechanical_gate_passed": action["mechanical_gate_passed"],
        "review_dir": str(review_root),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
