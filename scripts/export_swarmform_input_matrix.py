#!/usr/bin/env python3
"""Materialize the selected SwarmForm inputs without model calls."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "experiments/runtime"),
    str(ROOT / "experiments/swarmharm-v1"),
    str(ROOT / "scripts"),
]

import run_swarmform
from swarmform_scope import selected_cells
from swarmform.input_catalog import (
    IMPLEMENTED_ENCODINGS,
    build,
    deployment_registration,
    observation_registration,
    task_network,
)
from swarmform.inputs import digest


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def slug(value):
    return value.lower().replace(" ", "-")


def materialize(root, dataset_key, deployment, encoding, domain):
    visible, truth, manifest = build(
        dataset_key,
        domain,
        deployment=deployment,
        encoding=encoding,
        shared=True,
    )
    cell = root / deployment / encoding / slug(domain)
    cell.mkdir(parents=True)
    save(cell / "input.json", visible)
    save(cell / "protected-truth.json", truth)
    save(cell / "input-manifest.json", manifest)
    save(cell / "deployment.json", deployment_registration(manifest))
    save(cell / "observation.json", observation_registration(manifest, visible["startup"]))
    save(cell / "network.json", task_network(deployment))
    task_hashes = run_swarmform.write_tasks(
        cell,
        visible,
        run_swarmform.IMAGE,
        domain,
        deployment,
        manifest,
    )
    files = [
        "input.json",
        "protected-truth.json",
        "input-manifest.json",
        "deployment.json",
        "observation.json",
        "network.json",
        *sorted(task_hashes),
    ]
    package = {
        "matrix_cell": "/".join((deployment, encoding, domain)),
        "dataset_key": dataset_key,
        "population": len(visible["startup"]),
        "input_sha256": digest(manifest),
        "files": {name: sha(cell / name) for name in files},
        "model_calls": 0,
    }
    save(cell / "input-package.json", package)
    return package


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-key", default="november")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--accepted", action="store_true", help="Export the reviewed final input for each qualifying environment")
    parser.add_argument("--all-retained", action="store_true", help="Include all retained domains and configurations")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        parser.error("Choose a new output directory")
    if output.is_relative_to(ROOT):
        parser.error("Write generated input environments outside the repository")
    if args.accepted:
        from swarmform_delivery_export import export_accepted
        output.parent.mkdir(parents=True, exist_ok=True)
        index = export_accepted(ROOT, output, args.dataset_key, all_retained=args.all_retained)
        print(f"Exported {index['environments']} accepted environments to {output}")
        return
    output.mkdir(parents=True)
    ledger = json.loads((ROOT / 'docs/live-rollout-status.json').read_text())
    selected = selected_cells(ledger, all_retained=args.all_retained)
    rows = []
    for deployment, encoding, domain in selected:
        rows.append(materialize(output, args.dataset_key, deployment, encoding, domain))
    if len(rows) != len(selected) or len({row["matrix_cell"] for row in rows}) != len(selected):
        raise RuntimeError("The generated inputs differ from the selected scope")
    if len({row["input_sha256"] for row in rows}) != len(selected):
        raise RuntimeError("Two matrix cells produced the same effective input")
    index = {
        "kind": "swarmform_input_matrix",
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dataset_key": args.dataset_key,
        "input_environments": len(rows),
        "model_calls": 0,
        "scope": "all_retained" if args.all_retained else ledger['delivery_scope'],
        "cells": rows,
    }
    save(output / "index.json", index)
    print(json.dumps({
        "input_environments": len(rows),
        "deployments": len(IMPLEMENTED_ENCODINGS),
        "encodings_per_deployment": sorted({len(value) for value in IMPLEMENTED_ENCODINGS.values()}),
        "domains": len({cell[2] for cell in selected}),
        "model_calls": 0,
        "output": str(output),
    }))


if __name__ == "__main__":
    main()
