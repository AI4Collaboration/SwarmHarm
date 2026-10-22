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
REQUIRED_ADMISSION = {
    "causal_attribution",
    "native_transfer_provenance",
    "development_holdout_separation",
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
    admission_ids = {item["id"] for item in contract["dataset_admission_principles"]}
    if environment_ids != REQUIRED_ENVIRONMENT:
        fail(f"environment principles differ: {sorted(environment_ids)}")
    if admission_ids != REQUIRED_ADMISSION:
        fail(f"admission principles differ: {sorted(admission_ids)}")
    for item in contract["environment_conditions"]:
        if not item.get("evidence"):
            fail(f"{item['id']} has no evidence")
        for reference in item["evidence"]:
            validate_evidence(reference)

    audit = contract["current_environment_audit"]
    if audit["held_out"] or audit["eligible_for_final_estimation"]:
        fail("the tuned synthetic environment cannot be marked held out or final")
    environment = ROOT / audit["environment"]
    executable = harbor_python()
    for module in audit["offline_check_modules"]:
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
                "dataset_admission_principles": len(admission_ids),
                "environment": audit["environment"],
                "status": audit["status"],
                "eligible_for_final_estimation": audit["eligible_for_final_estimation"],
                "offline_check_modules": len(audit["offline_check_modules"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
