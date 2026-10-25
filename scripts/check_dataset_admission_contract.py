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
REQUIRED_RULES = {"connected_native_provenance", "independent_ground_truth"}


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
    for key in ("formation_environment", "harm_environment"):
        path = ROOT / status[key]
        if not path.exists():
            fail(f"missing current path {status[key]}")
    report = "docs/research/formation-v51-cue7-v32-paired-live-review-2026-10-25.md"
    if not (ROOT / report).is_file():
        fail("current paired formation review is missing")
    harm_report = "docs/research/cause-harm-v4-paired-live-review-2026-10-25.md"
    if not (ROOT / harm_report).is_file():
        fail("current paired harm review is missing")
    cue_report = "docs/research/cause-harm-v7-cue3-paired-live-review-2026-10-25.md"
    if not (ROOT / cue_report).is_file():
        fail("current cue-level harm review is missing")
    expected_formation = {
        "formation_result": "v32_matched_case_both_models_passed_formation",
        "positive_confirmation_result": "v31_both_models_passed_at_triage_cue",
        "paired_formation_result": "v51_cue7_both_models_passed_formation_glm_completed_transfer_deepseek_transfer_timed_out_after_fetch",
    }
    for key, expected in expected_formation.items():
        if status.get(key) != expected:
            fail(f"formation evidence is stale: {key}")
    if status.get("harm_result") != "v7_cue3_both_successors_exact_record_receipt_glm_source_effect_both_corrective_no_explicit_method":
        fail("harm result is stale")
    if status["formation_status"] != "v51_matched_case_live_confirmed":
        fail("formation status is stale")
    if status["harm_status"] != "v7_cue3_live_adoption_and_task-structure_boundary":
        fail("harm component status is stale")
    if status["integrated_end_to_end_status"] != "not_established":
        fail("integrated status is stale")
    if (
        status["current_gate_revision"]
        != "propensity-opportunity-v32"
        or status["permissions_revision"]
        != "propensity-opportunity-v51"
    ):
        fail("formation revision metadata is stale")
    if set(status["models"]) != {
        "deepseek/deepseek-v4.1-flash-1017", "z-ai/glm-5.3-flashx"
    }:
        fail("paired model routes are stale")
    if "reviewed_prior_revision" in status:
        fail("historical revision metadata must not remain in the active contract")
    print("dataset admission contract: valid")


if __name__ == "__main__":
    main()
