#!/usr/bin/env python3
"""Validate the maintained dataset contract and its evidence references."""

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/dataset-admission-contract.json"
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
    for item in value["environment_conditions"]:
        if not item.get("evidence"):
            fail(f"{item['id']} has no evidence")
        for reference in item["evidence"]:
            validate_reference(reference)
    status = value["current_status"]
    path = ROOT / status["environment"]
    if not path.exists():
        fail(f"missing current path {status['environment']}")
    report = status.get("latest_review", "")
    if not (ROOT / report).is_file():
        fail("current reviewed campaign report is missing")
    if status.get("current_status") != "v22_reviewed":
        fail("maintained campaign status is stale")
    if status.get("current_input_revision") != "continuous-formation-to-external-effect-v22":
        fail("continuous campaign revision metadata is stale")
    if status.get("current_phase1_gate_revision") != "propensity-opportunity-v34":
        fail("Phase 1 gate revision metadata is stale")
    if status.get("current_outcome_revision") != "deliberate-boundary-adoption-v9":
        fail("outcome revision metadata is stale")
    if status.get("phase1_status") != "passed":
        fail("Phase 1 status is stale")
    if status.get("phase2_status") != "valid_negative_in_procurement":
        fail("Phase 2 procurement result is stale")
    if status["integrated_end_to_end_status"] != "collective_misalignment_not_observed":
        fail("integrated status is stale")
    if status.get("iteration_model") != "z-ai/glm-5.3-flashx":
        fail("iteration model is stale")
    if status.get("next_environment") != "aggregate-budget-composition":
        fail("next environment is stale")
    print("dataset admission contract: valid")


if __name__ == "__main__":
    main()
