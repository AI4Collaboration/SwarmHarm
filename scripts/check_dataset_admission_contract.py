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
    report = "docs/research/formation-v51-cue7-v32-paired-live-review-2026-10-25.md"
    if not (ROOT / report).is_file():
        fail("current paired formation review is missing")
    if status.get("historical_phase1_result") != "v51_cue7_both_models_passed_formation":
        fail("historical Phase 1 evidence is stale")
    if status.get("current_status") != "continuous_campaign_live_rollout_pending":
        fail("maintained campaign must remain marked live rollout pending")
    if status.get("current_input_revision") != "continuous-formation-to-external-effect-v4":
        fail("continuous campaign revision metadata is stale")
    if status["integrated_end_to_end_status"] != "not_established":
        fail("integrated status is stale")
    if set(status["models"]) != {
        "deepseek/deepseek-v4.1-flash-1017", "z-ai/glm-5.3-flashx"
    }:
        fail("paired model routes are stale")
    if "reviewed_prior_revision" in status:
        fail("historical revision metadata must not remain in the active contract")
    print("dataset admission contract: valid")


if __name__ == "__main__":
    main()
