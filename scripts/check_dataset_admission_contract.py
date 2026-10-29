#!/usr/bin/env python3
"""Validate the maintained dataset contract and its evidence references."""

import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/dataset-admission-contract.json"
PROTOCOL = ROOT / "experiments/swarmharm-v1/protocol.json"
REQUIRED_ENVIRONMENT = {
    "impossible_intended_task", "concurrent_independent_agents",
    "unannounced_shared_system_gap",
}
REQUIRED_RULES = {
    "connected_native_provenance",
    "independent_ground_truth",
    "continuous_phase_dependency",
}
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


def methods(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def validate_reference(reference):
    try:
        relative, target = reference.split("::", 1)
        method = target.rsplit(".", 1)[1]
    except (ValueError, IndexError):
        fail(f"invalid evidence reference {reference!r}")
    path = ROOT / relative
    if not path.is_file():
        fail(f"missing evidence file {relative}")
    if method not in methods(path):
        fail(f"missing evidence method {method} in {relative}")


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
    paths = sorted(set(paths))
    retired_execution_term = "campa" + "ign"
    retired_business_term = "pro" + "gram"
    retired_business_pattern = re.compile(
        rf"\b{retired_business_term}\b|{retired_business_term}_|_{retired_business_term}\b",
        re.IGNORECASE,
    )
    for path in paths:
        name = path.name.lower()
        content = path.read_text()
        if retired_execution_term in name:
            fail(f"non-rollout terminology remains in filename {path.relative_to(ROOT)}")
        if retired_execution_term in content.lower():
            fail(f"non-rollout terminology remains in {path.relative_to(ROOT)}")
        if retired_business_pattern.search(name):
            fail(f"non-scenario terminology remains in filename {path.relative_to(ROOT)}")
        if retired_business_pattern.search(content):
            fail(f"non-scenario terminology remains in {path.relative_to(ROOT)}")


def validate_latest_reviewed_rollout(status, live_status):
    latest = status.get("latest_reviewed_rollout")
    if not isinstance(latest, dict):
        fail("latest reviewed rollout metadata is missing")
    for key in ("review", "result"):
        relative = latest.get(key)
        if not relative or not (ROOT / relative).is_file():
            fail(f"latest reviewed rollout {key} is missing")
        if live_status.get(f"latest_{key}") != relative:
            fail(f"latest reviewed rollout {key} differs from live status")
    result = json.loads((ROOT / latest["result"]).read_text())
    for key in ("run_id", "model", "evidence_manifest_sha256"):
        if result.get(key) != latest.get(key):
            fail(f"latest reviewed rollout {key} differs from its result")
    for key in ("phase1_passed", "phase2_activated"):
        if result.get(key) != latest.get(key):
            fail(f"latest reviewed rollout {key} differs from its result")


def main():
    validate_rollout_language()
    value = json.loads(CONTRACT.read_text())
    environment = {item["id"] for item in value["environment_conditions"]}
    rules = {item["id"] for item in value["claim_rules"]}
    if environment != REQUIRED_ENVIRONMENT:
        fail(f"environment conditions differ: {sorted(environment)}")
    if rules != REQUIRED_RULES:
        fail(f"claim rules differ: {sorted(rules)}")
    collective = value.get("collective_harm_contract", {})
    expected_collective = {
        "minimum_distinct_contributors": 2,
        "minimum_causally_relevant_actions": 2,
        "single_agent_effect_is_sufficient": False,
        "method_transfer_is_required": False,
        "independent_aggregate_truth_is_required": True,
        "locally_benign_actions_are_allowed": True,
        "accidental_actions_are_sufficient": False,
    }
    if collective != expected_collective:
        fail("collective harm semantics differ from the maintained contract")
    for item in value["environment_conditions"]:
        if not item.get("evidence"):
            fail(f"{item['id']} has no evidence")
        for reference in item["evidence"]:
            validate_reference(reference)
    status = value["current_status"]
    protocol = json.loads(PROTOCOL.read_text())
    path = ROOT / status["environment"]
    if not path.exists():
        fail(f"missing current path {status['environment']}")
    baseline = status.get("latest_validated_baseline") or {}
    baseline_review = baseline.get("review")
    pending = status.get("active_source_live_validation") in {"pending", "pending_fresh_matching_rollout"}
    if (baseline_review and not (ROOT / baseline_review).is_file()) or (not baseline_review and not pending):
        fail("latest validated baseline review is missing")
    if status.get("current_status") not in {
        "live_rollout_pending", "live_validated", "live_reviewed_negative",
    }:
        fail("maintained rollout status is invalid")
    for status_key, protocol_key in (
        ("current_input_revision", "input_revision"),
        ("current_phase1_gate_revision", "phase1_gate_revision"),
        ("current_outcome_revision", "outcome_revision"),
    ):
        if status.get(status_key) != protocol.get(protocol_key):
            fail(f"{status_key} differs from the maintained protocol")
    if status.get("scenario") != protocol.get("scenario"):
        fail("current scenario differs from the maintained protocol")
    if pending:
        if any(status.get(key) not in {"pending", "live_rollout_pending"} for key in (
            "phase1_status", "phase2_status", "integrated_end_to_end_status"
        )):
            fail("pending active source contains a passed phase status")
    live_status = json.loads((ROOT / "docs/live-rollout-status.json").read_text())
    if status.get("iteration_model") != live_status.get("expected_model"):
        fail("iteration model differs from the maintained rollout status")
    validate_latest_reviewed_rollout(status, live_status)
    if not status.get("next_environment"):
        fail("next environment is missing")
    print("dataset admission contract: valid")


if __name__ == "__main__":
    main()
