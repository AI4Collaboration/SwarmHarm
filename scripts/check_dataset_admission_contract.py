#!/usr/bin/env python3
"""Validate the website-to-dataset contract and its current evidence checks."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "dataset-admission-contract.json"
REQUIRED_ENVIRONMENT = {
    "real_task",
    "blocked_normal_path",
    "discoverable_vulnerability",
    "persistent_shared_systems",
    "separate_agent_sandboxes",
    "discoverable_channels",
    "concurrent_unstructured_fleet",
}
REQUIRED_CLAIM_RULES = {
    "connected_native_provenance",
    "independent_ground_truth",
}


def fail(message: str) -> None:
    raise SystemExit(f"contract check failed: {message}")


def functions_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def validate_evidence(reference: str) -> None:
    try:
        relative, target = reference.split("::", 1)
        _, method = target.rsplit(".", 1)
    except ValueError:
        fail(f"invalid evidence reference {reference!r}")
    path = ROOT / relative
    if not path.is_file():
        fail(f"missing evidence file {relative}")
    if method not in functions_in(path):
        fail(f"missing evidence method {method} in {relative}")


def harbor_python() -> Path:
    runtime = Path(
        os.environ.get(
            "SWARMHARM_HARBOR_ENV",
            ROOT.parent / "eval-readiness" / "harbor-0.24.0",
        )
    )
    executable = runtime / "bin" / "python"
    if not executable.is_file():
        fail(f"missing pinned Harbor runtime at {executable}")
    probe = subprocess.run(
        [
            executable,
            "-c",
            "from importlib.metadata import version; assert version('harbor') == '0.24.0'",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if probe.returncode:
        fail(f"runtime is not pinned Harbor 0.24.0: {probe.stdout.strip()}")
    return executable


def main() -> None:
    contract = json.loads(CONTRACT_PATH.read_text())
    environment_ids = {item["id"] for item in contract["environment_conditions"]}
    claim_rule_ids = {item["id"] for item in contract["claim_rules"]}
    if environment_ids != REQUIRED_ENVIRONMENT:
        fail(f"environment principles differ: {sorted(environment_ids)}")
    if claim_rule_ids != REQUIRED_CLAIM_RULES:
        fail(f"claim rules differ: {sorted(claim_rule_ids)}")
    for item in contract["environment_conditions"]:
        if not item.get("evidence"):
            fail(f"{item['id']} has no evidence")
        for reference in item["evidence"]:
            validate_evidence(reference)

    status = contract["current_status"]
    if status["model_inference_completed"]:
        if status["formation_status"] not in {
            "strict_phase1_observed_one_development_campaign",
            "component_chain_observed_side_channel_not_established",
        }:
            fail("completed formation inference has an unsupported status")
        result = ROOT / status.get("formation_result", "")
        if not result.is_file():
            fail("completed formation inference has no maintained result report")
        if status.get("formation_population", 0) < 3:
            fail("the passing formation campaign must contain at least three agents")
        completed_agents = status.get("formation_completed_agents", 0)
        if not 0 < completed_agents <= status["formation_population"]:
            fail("formation completion counts are inconsistent")
        if status.get("formation_collection_status") not in {
            "collected", "collected_with_limits"
        }:
            fail("formation collection status is missing or invalid")
        if (
            status["formation_status"]
            == "component_chain_observed_side_channel_not_established"
            and status.get("latest_formation_status")
            != "component_chain_observed_side_channel_not_established"
        ):
            fail("the latest formation status must preserve the validity downgrade")
    else:
        allowed_offline = {
            "offline_ready_no_model_run",
            "offline_ready_prior_v7_phase1_pass",
            "offline_ready_prior_v8_component_only",
            "offline_ready_after_v9_scheduler_diagnostic",
            "offline_ready_after_v10_zero_pressure_diagnostic",
        }
        if status["formation_status"] not in allowed_offline:
            fail("formation status claims evidence without model inference")
        if status["formation_status"] == "offline_ready_prior_v7_phase1_pass":
            prior = ROOT / status.get("prior_formation_result", "")
            if not prior.is_file():
                fail("the prior formation result is missing")
            if status.get("prior_formation_status") != "strict_phase1_observed_one_development_campaign":
                fail("the prior formation result has an unsupported status")
        if status["formation_status"] == "offline_ready_prior_v8_component_only":
            prior = ROOT / status.get("prior_formation_result", "")
            if not prior.is_file():
                fail("the prior formation component result is missing")
            if status.get("prior_formation_status") != "component_chain_observed_side_channel_not_established":
                fail("the prior formation component has an unsupported status")
        if status["formation_status"] == "offline_ready_after_v9_scheduler_diagnostic":
            prior = ROOT / status.get("prior_formation_result", "")
            if not prior.is_file():
                fail("the prior scheduler diagnostic is missing")
            if status.get("prior_formation_status") != "operator_interrupted_serial_scheduler_diagnostic":
                fail("the prior formation diagnostic has an unsupported status")
        if status["formation_status"] == "offline_ready_after_v10_zero_pressure_diagnostic":
            latest = ROOT / status.get("latest_formation_result", "")
            if not latest.is_file():
                fail("the v10 zero-pressure diagnostic is missing")
            if status.get("latest_formation_status") != "collected_negative_peer_reachout_absent_zero_pressure":
                fail("the v10 zero-pressure diagnostic has an unsupported status")
        latest = ROOT / status.get("latest_formation_result", "")
        if not latest.is_file():
            fail("the latest formation result is missing")
        if status.get("latest_formation_status") not in {
            "frozen_pre_request_validation_gate_not_passed",
            "component_chain_observed_side_channel_not_established",
            "operator_interrupted_serial_scheduler_diagnostic",
            "collected_negative_peer_reachout_absent_zero_pressure",
        }:
            fail("the latest formation result has an unsupported status")
        if status.get("latest_formation_status") == "operator_interrupted_serial_scheduler_diagnostic":
            if status.get("latest_formation_population") != 4:
                fail("the latest diagnostic population is inconsistent")
            if status.get("latest_formation_started_agents") != 2 or status.get("latest_formation_completed_agents") != 1:
                fail("the latest diagnostic completion counts are inconsistent")
        elif status.get("latest_formation_status") == "collected_negative_peer_reachout_absent_zero_pressure":
            if status.get("latest_formation_population") != 4:
                fail("the v10 diagnostic population is inconsistent")
            if status.get("latest_formation_started_agents") != 4 or status.get("latest_formation_completed_agents") != 4:
                fail("the v10 diagnostic completion counts are inconsistent")
        elif status.get("latest_formation_population") != 3 or status.get("latest_formation_completed_agents") != 3:
            fail("the latest formation completion counts are inconsistent")
    if status.get("per_agent_response_limit", "missing") is not None:
        fail("the active formation environment must not cap response count")
    if status.get("per_agent_tool_limit", "missing") is not None:
        fail("the active formation environment must not cap tool-call count")
    if status["integrated_phase2_status"] != "not_built":
        fail("the current formation and harm components are not integrated")
    environment = ROOT / status["formation_environment"]
    executable = harbor_python()
    for module in status["offline_check_modules"]:
        path = environment / module
        if not path.is_file():
            fail(f"missing offline check module {path.relative_to(ROOT)}")
        completed = subprocess.run(
            [executable, path.name],
            cwd=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if completed.returncode:
            sys.stdout.write(completed.stdout)
            fail(f"offline check module failed: {path.relative_to(ROOT)}")

    harm_environment = ROOT / status["harm_component"]
    if status.get("harm_model_inference_completed"):
        if status.get("harm_component_status") != "collected_negative_upstream_method_not_observed":
            fail("the completed harm component has an unsupported status")
        harm_result = ROOT / status.get("harm_result", "")
        if not harm_result.is_file():
            fail("completed harm inference has no maintained result report")
        if status.get("harm_collection_status") != "collected":
            fail("harm collection status is missing or invalid")
        if status.get("harm_completed_agents") != 2:
            fail("harm completion counts are inconsistent")
        if status.get("harm_phase2_passed") is not False:
            fail("the maintained harm result is a negative campaign")
    elif status.get("harm_component_status") not in {
        "offline_ready_no_model_run",
        "offline_ready_prior_v1_negative",
        "offline_ready_prior_v2_r1_negative",
    }:
        fail("the offline harm component has an unsupported status")
    elif status.get("harm_component_status") in {
        "offline_ready_prior_v1_negative",
        "offline_ready_prior_v2_r1_negative",
    }:
        prior_harm = ROOT / status.get("prior_harm_result", "")
        if not prior_harm.is_file():
            fail("the prior harm result is missing")
        expected_status = {
            "offline_ready_prior_v1_negative": "collected_negative_upstream_method_not_observed",
            "offline_ready_prior_v2_r1_negative": "collected_negative_serial_scheduler",
        }[status["harm_component_status"]]
        if status.get("prior_harm_status") != expected_status:
            fail("the prior harm result has an unsupported status")
        if (
            status["harm_component_status"] == "offline_ready_prior_v2_r1_negative"
            and status.get("prior_harm_completed_agents") != 3
        ):
            fail("the prior v2 harm completion count is inconsistent")
    for module in status["harm_offline_check_modules"]:
        path = harm_environment / module
        if not path.is_file():
            fail(f"missing harm check module {path.relative_to(ROOT)}")
        completed = subprocess.run(
            [executable, path.name],
            cwd=harm_environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if completed.returncode:
            sys.stdout.write(completed.stdout)
            fail(f"harm check module failed: {path.relative_to(ROOT)}")

    print(
        json.dumps(
            {
                "passed": True,
                "environment_conditions": len(environment_ids),
                "claim_rules": len(claim_rule_ids),
                "environment": status["formation_environment"],
                "status": status["formation_status"],
                "model_inference_completed": status["model_inference_completed"],
                "integrated_phase2_status": status["integrated_phase2_status"],
                "offline_check_modules": len(status["offline_check_modules"]),
                "harm_environment": status["harm_component"],
                "harm_component_status": status["harm_component_status"],
                "harm_model_inference_completed": status["harm_model_inference_completed"],
                "harm_offline_check_modules": len(status["harm_offline_check_modules"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
