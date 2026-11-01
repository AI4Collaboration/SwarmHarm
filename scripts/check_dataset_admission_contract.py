#!/usr/bin/env python3
"""Validate the maintained independent-phase contract and current evidence."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/dataset-admission-contract.json"
STATUS = ROOT / "docs/live-rollout-status.json"
REGISTRATIONS = ROOT / "experiments/swarmharm-v1/registrations"
ROLLOUT_LANGUAGE_PATHS = [
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "experiments/swarmharm-v1/README.md",
    ROOT / "experiments/swarmharm-v1/format-contract.json",
    ROOT / "experiments/swarmharm-v1/protocol.json",
    ROOT / "experiments/swarmharm-v1/domain-scenarios.json",
]


def fail(message):
    raise SystemExit("contract check failed: " + message)


def validate_rollout_language():
    paths = ROLLOUT_LANGUAGE_PATHS + sorted((ROOT / "docs").rglob("*.md"))
    paths += sorted((ROOT / "docs").rglob("*.json"))
    for source_root in (
        ROOT / "experiments/swarmharm-v1",
        ROOT / "experiments/prompt-contract",
    ):
        for suffix in ("*.py", "*.json", "*.md"):
            paths += [
                path for path in source_root.rglob(suffix)
                if "registrations" not in path.parts
            ]
    retired_execution_term = "campa" + "ign"
    retired_business_term = "pro" + "gram"
    retired_business_pattern = re.compile(
        rf"\b{retired_business_term}\b|{retired_business_term}_|_{retired_business_term}\b",
        re.IGNORECASE,
    )
    for path in sorted(set(paths)):
        content = path.read_text()
        if retired_execution_term in path.name.lower() or retired_execution_term in content.lower():
            fail(f"non-rollout terminology remains in {path.relative_to(ROOT)}")
        if retired_business_pattern.search(path.name) or retired_business_pattern.search(content):
            fail(f"non-scenario terminology remains in {path.relative_to(ROOT)}")


def main():
    validate_rollout_language()
    contract = json.loads(CONTRACT.read_text())
    status = json.loads(STATUS.read_text())

    if contract.get("active_scope") != "phase2-only":
        fail("current development scope must remain Phase 2 only")
    if status.get("active_scope") != "phase2-only":
        fail("live status does not mark Phase 2-only development")

    architecture = contract.get("architecture", {})
    if not architecture.get("phase1_and_phase2_independent"):
        fail("Phase 1 and Phase 2 are not marked independent")
    if architecture.get("independent_phase2_makes_formation_claim"):
        fail("independent Phase 2 cannot make a formation claim")

    phase1 = contract.get("phase1", {})
    if phase1.get("minimum_agents") != 4 or phase1.get("selected_baseline") != "r136":
        fail("Phase 1 baseline contract differs")
    if phase1.get("development_status") != "frozen_reference_not_current_gate":
        fail("Phase 1 must remain a frozen reference, not a current gate")
    if phase1.get("announced_peers") or phase1.get("announced_channel"):
        fail("Phase 1 must not announce peers or channel")

    phase2 = contract.get("phase2", {})
    if phase2.get("minimum_distinct_causal_contributors") != 2:
        fail("Phase 2 contributor minimum differs")
    if not phase2.get("independent_terminal_outcome_required"):
        fail("Phase 2 terminal outcome is not independently verified")
    if phase2.get("reply_roundtrip_required"):
        fail("Phase 2 incorrectly requires another reply round trip")
    if not phase2.get("supplied_method_must_be_labeled"):
        fail("supplied method provenance is not required")

    for relative in contract.get("current_evidence", {}).values():
        if not (ROOT / relative).is_file():
            fail(f"missing current evidence {relative}")

    if status.get("status") != "no_active_rollout" or status.get("active_rollouts"):
        fail("unexpected active rollout")
    expected = set(status.get("maintained_registrations", []))
    actual = {path.name for path in REGISTRATIONS.iterdir() if path.is_dir()}
    if actual != expected:
        fail(f"maintained registrations differ: {sorted(actual ^ expected)}")
    if not (ROOT / status["decision_record"]).is_file():
        fail("current decision record is missing")

    print("dataset admission contract: valid")


if __name__ == "__main__":
    main()
