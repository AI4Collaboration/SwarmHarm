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
    for key in (
        "formation_result", "positive_confirmation_result",
        "paired_formation_result", "harm_result",
    ):
        if status[key] is not None:
            fail(f"pending status must not reference a historical result: {key}")
    if status["formation_status"] != "paired_live_rollout_pending":
        fail("formation status is stale")
    if (
        status["current_gate_revision"]
        != "propensity-opportunity-v28"
        or status["permissions_revision"]
        != "propensity-opportunity-v40"
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
