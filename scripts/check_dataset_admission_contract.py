#!/usr/bin/env python3
"""Validate the maintained dataset contract and its evidence references."""

import ast
import json
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


def main():
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
    baseline = status.get("latest_validated_baseline", {})
    baseline_review = baseline.get("review")
    if not baseline_review or not (ROOT / baseline_review).is_file():
        fail("latest validated baseline review is missing")
    if status.get("current_status") not in {
        "glm_default_source_live_rollout_pending",
        "glm_default_source_live_validated",
    }:
        fail("maintained campaign status is invalid")
    for status_key, protocol_key in (
        ("current_input_revision", "input_revision"),
        ("current_phase1_gate_revision", "phase1_gate_revision"),
        ("current_outcome_revision", "outcome_revision"),
    ):
        if status.get(status_key) != protocol.get(protocol_key):
            fail(f"{status_key} differs from the maintained protocol")
    if status.get("scenario") != protocol.get("scenario"):
        fail("current scenario differs from the maintained protocol")
    if status.get("active_source_live_validation") == "pending_fresh_matching_campaign":
        if any(status.get(key) != "live_rollout_pending" for key in (
            "phase1_status", "phase2_status", "integrated_end_to_end_status"
        )):
            fail("pending active source contains a passed phase status")
    if status.get("iteration_model") != "z-ai/glm-5.3":
        fail("iteration model is stale")
    if not status.get("next_environment"):
        fail("next environment is missing")
    print("dataset admission contract: valid")


if __name__ == "__main__":
    main()
