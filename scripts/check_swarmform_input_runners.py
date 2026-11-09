#!/usr/bin/env python3
"""Check and list the offline witness runner for every SwarmForm input cell."""

import argparse
from itertools import product
import json
from pathlib import Path


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
                "--encoding", encoding, "--smoke", "--output", output]
    if deployment in ("artifact_namespace", "job_namespace"):
        command = ["scripts/check_swarmform_service_inputs.py", "smoke",
                "--deployment", deployment, "--encoding", encoding,
                "--domain", domain, "--output", output]
        if encoding == "timing":
            command += ["--payload-bytes", "16"]
        return command
    raise ValueError(deployment)


def matrix():
    rows = []
    for deployment, encoding, domain in product(DEPLOYMENTS, ENCODINGS, DOMAINS):
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
            "model_calls": 0,
        })
    if len(rows) != 100 or len({row["matrix_cell"] for row in rows}) != 100:
        raise AssertionError("Runner routing does not cover the 5 x 5 x 4 matrix")
    if len({(row["deployment"], row["encoding"]) for row in rows}) != 25:
        raise AssertionError("Runner routing does not cover all 25 mechanisms")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", help="Print the runner for deployment/encoding/domain")
    parser.add_argument("--output", type=Path,
                        help="Optional JSON path for the complete routing matrix")
    args = parser.parse_args(argv)
    rows = matrix()
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
