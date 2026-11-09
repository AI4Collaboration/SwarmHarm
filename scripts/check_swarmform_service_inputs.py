"""Validate the 40 service cells and smoke one actual parameter combination.

No model is called.  Smoke commands are operator-authored feasibility checks,
not evidence of evaluated-agent behaviour and not part of the worker input.
"""

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import shlex
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "experiments/runtime"), str(ROOT / "experiments/swarmharm-v1"), str(ROOT / "scripts")]

from swarmform.archive_deployment import ArtifactDeployment
from swarmform.artifact_inputs import build as build_artifact
from swarmform.inputs import digest
from swarmform.job_deployment import JobDeployment
from swarmform.job_inputs import build as build_job
from swarmform_service_witness_codecs import (ARTIFACT_PUBLISH, ARTIFACT_RECEIVE,
    JOB_PREPARE, JOB_PUBLISH, JOB_RECEIVE)


DOMAINS = ("Data Analysis", "Engineering", "Financial Analysis", "Knowledge Work")
ENCODINGS = {
    "payload_content": "content",
    "identifiers_metadata": "metadata",
    "operational_state": "state",
    "event_pattern": "events",
    "timing": "timing",
}
DEPLOYMENTS = {
    "artifact_namespace": (build_artifact, ArtifactDeployment, "/workspace/archive.json"),
    "job_namespace": (build_job, JobDeployment, "/workspace/processing.json"),
}


def build_input(deployment, domain, profile, shared):
    builder = DEPLOYMENTS[deployment][0]
    if deployment == "artifact_namespace":
        return builder(domain, "november", profile=profile, shared=shared)
    return builder("november", domain, profile=profile, shared=shared)


def validate_matrix(output):
    rows = []
    for deployment, (_, _, connection) in DEPLOYMENTS.items():
        for encoding, profile in ENCODINGS.items():
            for domain in DOMAINS:
                shared_input, shared_truth, shared_manifest = build_input(deployment, domain, profile, True)
                private_input, private_truth, private_manifest = build_input(deployment, domain, profile, False)
                assert (shared_input, shared_truth) == (private_input, private_truth), (
                    deployment, profile, domain, "scope changed the business input")
                assert all(connection in files and "/workspace/work-order.md" in files
                           for files in shared_input["startup"].values())
                effective = shared_manifest["effective_settings"]
                registered_profile = effective.get("catalog_profile", effective.get("processing_profile"))
                assert effective["deployment"] == deployment and registered_profile == profile
                assert (private_manifest["worker_visible_sha256"] ==
                        shared_manifest["worker_visible_sha256"])
                rows.append({"deployment": deployment, "encoding": encoding, "profile": profile, "domain": domain,
                    "worker_visible_sha256": shared_manifest["worker_visible_sha256"],
                    "input_sha256": digest(shared_manifest), "matched_private_worker_input": True})
    passed = (len(rows) == 40
              and len({(row["deployment"], row["encoding"], row["domain"])
                       for row in rows}) == 40
              and len({row["input_sha256"] for row in rows}) == 40)
    result = {"model_calls": 0, "operator_authored": True,
              "cells": len(rows), "passed": passed, "rows": rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def command(script, *values):
    return "python -c " + shlex.quote(script) + " " + " ".join(
        shlex.quote(str(value)) for value in values)


def payload(label, count):
    result = b""
    index = 0
    while len(result) < count:
        result += sha256(label.encode() + index.to_bytes(4, "big")).digest()
        index += 1
    return result[:count]


def smoke(deployment_name, encoding, domain, shared, output, payload_bytes):
    profile = ENCODINGS[encoding]
    inputs, _, manifest = build_input(deployment_name, domain, profile, shared)
    owner, reader = tuple(inputs["startup"])[:2]
    # Callers normally choose a small timing payload because a protected-clock
    # transfer is intentionally slower; the mechanism itself is not size-capped.
    actual_bytes = payload_bytes
    raw = payload(f"{deployment_name}/{profile}/{domain}", actual_bytes)
    encoded = base64.b64encode(raw).decode()
    deployment_class = DEPLOYMENTS[deployment_name][1]
    output.mkdir(parents=True, exist_ok=False)
    (output / "input.json").write_text(json.dumps(inputs, indent=2) + "\n")
    (output / "input-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    started = time.monotonic()
    with deployment_class(inputs["startup"], shared=shared, profile=profile,
                          observation_archive=output / "observations") as deployment:
        if deployment_name == "artifact_namespace":
            sent_result, _ = deployment.execute(owner, command(ARTIFACT_PUBLISH, profile, encoded))
            assert sent_result["exit_code"] == 0, sent_result
            sent = json.loads(sent_result["stdout"])
            received_result, _ = deployment.execute(reader, command(
                ARTIFACT_RECEIVE, profile, owner, sent["first"], sent["last"], sent["count"]))
        else:
            bits = len(raw) * 8
            prepared_result, _ = deployment.execute(owner, command(
                JOB_PREPARE, profile, max(bits + 1, 2)))
            assert prepared_result["exit_code"] == 0, prepared_result
            prepared = prepared_result["stdout"].strip()
            sent_result, _ = deployment.execute(owner, command(JOB_PUBLISH, profile, encoded, prepared))
            assert sent_result["exit_code"] == 0, sent_result
            sent = json.loads(sent_result["stdout"])
            received_result, _ = deployment.execute(reader, command(JOB_RECEIVE, profile, owner,
                sent["first"], sent["last"], sent["count"], sent.get("after", 0)))
        assert received_result["exit_code"] == 0, received_result
        received = json.loads(received_result["stdout"])
        bindings = deployment.bindings
    assert received.get("visible", False) == shared, received
    if shared:
        assert received["bytes"] == len(raw), received
        assert received["sha256"] == sha256(raw).hexdigest(), received
    result = {"model_calls": 0, "operator_authored": True,
        "deployment": deployment_name, "encoding": encoding, "profile": profile, "domain": domain,
        "shared": shared, "payload_bytes": len(raw), "transferred": bool(received.get("visible")),
        "payload_sha256": sha256(raw).hexdigest(), "elapsed_seconds": time.monotonic() - started,
        "resources_closed": deployment.closed, "bindings": bindings,
        "scope": "Operator feasibility witness; not evaluated-agent behaviour evidence."}
    (output / "witness.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    matrix = sub.add_parser("matrix")
    matrix.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("smoke")
    run.add_argument("--deployment", choices=DEPLOYMENTS, required=True)
    run.add_argument("--encoding", choices=ENCODINGS, required=True)
    run.add_argument("--domain", choices=DOMAINS, required=True)
    run.add_argument("--scope", choices=("both", "shared", "private"), default="both")
    run.add_argument("--payload-bytes", type=int, default=256)
    run.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "matrix":
        output = args.output.resolve()
        if output.exists() or output.is_relative_to(ROOT):
            parser.error("Choose a new output file outside the repository")
        result = validate_matrix(output)
    else:
        if not 1 <= args.payload_bytes <= 8192:
            parser.error("--payload-bytes must be between 1 and 8192")
        output = args.output.resolve()
        if output.exists() or output.is_relative_to(ROOT):
            parser.error("Choose a new output path outside the repository")
        scopes = (True, False) if args.scope == "both" else (args.scope == "shared",)
        result = {"deployment": args.deployment, "encoding": args.encoding,
                  "domain": args.domain, "model_calls": 0,
                  "results": [smoke(args.deployment, args.encoding, args.domain, shared,
                                    output / ("shared" if shared else "private"),
                                    args.payload_bytes)
                              for shared in scopes]}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
