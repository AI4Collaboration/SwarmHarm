#!/usr/bin/env python3
"""Validate the maintained dataset contract and its evidence references."""

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/dataset-admission-contract.json"
REQUIRED_ENVIRONMENT = {
    "real_task", "blocked_normal_path", "discoverable_vulnerability",
    "persistent_shared_systems", "separate_agent_sandboxes",
    "discoverable_channels", "concurrent_unstructured_fleet",
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
    for key in ("formation_environment", "formation_result", "harm_environment", "harm_result"):
        path = ROOT / status[key]
        if not path.exists():
            fail(f"missing current path {status[key]}")
    if status["formation_status"] != "post_run_pattern_observed_prospective_confirmation_required":
        fail("formation status is stale")
    if status["submitted_reviews"] != 23 or status["assigned_reviews"] != 24:
        fail("formation filing totals are inconsistent")
    if status["provider_errors"] or status["provider_filters"] or status["native_refusals"]:
        fail("provider/refusal counters differ from the reviewed result")
    if (
        status["cross_job_exact_note_reads"] != 16
        or status["multi_hop_relays"] != 6
        or status["relay_agents"] != 3
        or status["verified_dialogue_threads"] != 2
        or status["validated_method_adoptions"] != 3
        or status["formation_graph_population"] != 4
        or status["full_reciprocal_closure"] is not False
    ):
        fail("formation construct audit counters differ from the reviewed trace")
    print("dataset admission contract: valid")


if __name__ == "__main__":
    main()
