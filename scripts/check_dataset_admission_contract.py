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
        if status["formation_status"] != "strict_phase1_observed_one_development_campaign":
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
    else:
        allowed_offline = {
            "offline_ready_no_model_run",
            "offline_ready_prior_v7_phase1_pass",
        }
        if status["formation_status"] not in allowed_offline:
            fail("formation status claims evidence without model inference")
        if status["formation_status"] == "offline_ready_prior_v7_phase1_pass":
            prior = ROOT / status.get("prior_formation_result", "")
            if not prior.is_file():
                fail("the prior formation result is missing")
            if status.get("prior_formation_status") != "strict_phase1_observed_one_development_campaign":
                fail("the prior formation result has an unsupported status")
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
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
