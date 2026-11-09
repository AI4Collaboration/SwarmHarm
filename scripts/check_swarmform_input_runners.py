#!/usr/bin/env python3
"""Check and list the offline witness runner for every SwarmForm input cell."""

import argparse
import json
from pathlib import Path
from swarmform_scope import selected_cells


ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ("Engineering", "Data Analysis", "Financial Analysis", "Knowledge Work")
ENCODINGS = (
    "payload_content",
    "identifiers_metadata",
    "operational_state",
    "event_pattern",
    "timing",
)
DEPLOYMENTS = (
    "shared_files",
    "shared_ipc",
    "worker_endpoint",
    "artifact_namespace",
    "job_namespace",
)
def runner(deployment, encoding, domain, output="{output}"):
    """Return the concrete no-model witness command for one matrix cell."""
    if deployment == "shared_files":
        scripts = {
            "payload_content": "scripts/check_swarmform_domain_deployment.py",
            "identifiers_metadata": "scripts/check_swarmform_file_metadata.py",
            "operational_state": "scripts/check_swarmform_file_state.py",
            "event_pattern": "scripts/check_swarmform_file_events.py",
            "timing": "scripts/check_swarmform_file_timing.py",
        }
        if encoding not in scripts:
            raise ValueError(encoding)
        if encoding == "payload_content" and domain == "Data Analysis":
            return ["scripts/check_swarmform_file_deployment.py", "--dataset-key", "november",
                    "--output", output]
        return [scripts[encoding], "--domain", domain, "--output", output]
    if deployment == "shared_ipc":
        return ["scripts/check_swarmform_ipc_inputs.py", "--domain", domain,
                "--encoding", encoding, "--output", output]
    if deployment == "worker_endpoint":
        return ["scripts/check_swarmform_endpoint_inputs.py", "--domain", domain,
                "--encoding", encoding, "--business", "--output", output]
    if deployment in ("artifact_namespace", "job_namespace"):
        return ["scripts/check_swarmform_service_inputs.py", "business",
                "--deployment", deployment, "--encoding", encoding,
                "--domain", domain, "--output", output]
    raise ValueError(deployment)


def matrix(*, all_retained=False):
    rows = []
    ledger = json.loads((ROOT / "docs/live-rollout-status.json").read_text())
    selected = selected_cells(ledger, all_retained=all_retained)
    for deployment, encoding, domain in selected:
        command = runner(deployment, encoding, domain)
        script = ROOT / command[0]
        if not script.is_file():
            raise FileNotFoundError(script)
        rows.append({
            "matrix_cell": "/".join((deployment, encoding, domain)),
            "deployment": deployment,
            "encoding": encoding,
            "domain": domain,
            "runner": command,
            "validation_scope": "full_business_workload",
            "model_calls": 0,
        })
    if len(rows) != len(selected) or len({row["matrix_cell"] for row in rows}) != len(selected):
        raise AssertionError("Runner routing differs from the selected scope")
    if len({(row["deployment"], row["encoding"]) for row in rows}) != 25:
        raise AssertionError("Runner routing does not cover all 25 mechanisms")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-retained", action="store_true", help="Include supplemental configurations")
    parser.add_argument("--cell", help="Print the runner for deployment/encoding/domain")
    parser.add_argument("--output", type=Path,
                        help="Optional JSON path for the complete routing matrix")
    args = parser.parse_args(argv)
    rows = matrix(all_retained=args.all_retained or bool(args.cell))
    if args.cell:
        matches = [row for row in rows if row["matrix_cell"] == args.cell]
        if not matches:
            parser.error("Unknown matrix cell")
        print(json.dumps(matches[0]))
        return
    report = {
        "kind": "swarmform_input_runner_matrix",
        "input_environments": len(rows),
        "mechanisms": len({(row["deployment"], row["encoding"]) for row in rows}),
        "model_calls": 0,
        "cells": rows,
    }
    if args.output:
        destination = args.output.resolve()
        if destination.exists() or destination.is_relative_to(ROOT):
            parser.error("Choose a new output file outside the repository")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in
                      ("input_environments", "mechanisms", "model_calls")}))


if __name__ == "__main__":
    main()
