#!/usr/bin/env python3
"""Reject stale live-validation claims for the maintained continuous campaign."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "docs/live-rollout-status.json"
PROTOCOL_PATH = ROOT / "experiments/swarmharm-v1/protocol.json"

# A reviewed live rollout binds both the live collection path and the evaluator
# that interprets it. Exports, tests and prose can change independently.
LIVE_EXECUTION_PATHS = {
    "experiments/swarmharm-v1/run.py",
    "experiments/swarmharm-v1/review.py",
    "experiments/swarmharm-v1/integrated_review.py",
    "experiments/swarmharm-v1/protocol.json",
    "experiments/swarmharm-v1/harbor_input.py",
    "experiments/swarmharm-v1/mechanics.py",
    "experiments/swarmharm-v1/lab.py",
    "experiments/swarmharm-v1/topology.py",
    "experiments/swarmharm-v1/schedule.py",
    "experiments/swarmharm-v1/launch.py",
    "experiments/swarmharm-v1/continuation.py",
    "experiments/swarmharm-v1/harm_mechanics.py",
    "experiments/runtime/atomic.py",
    "experiments/runtime/guardrails.py",
    "experiments/runtime/workstation.py",
    "experiments/runtime/transport.py",
    "experiments/runtime/response_monitor.py",
}


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def fail(message):
    raise SystemExit("live rollout status check failed: " + message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-confirmed", action="store_true",
        help="fail when the current environment is correctly marked pending",
    )
    args = parser.parse_args()
    status = load(STATUS_PATH)
    protocol = load(PROTOCOL_PATH)
    for key in ("input_revision", "phase1_gate_revision", "outcome_revision"):
        if status.get(key) != protocol.get(key):
            fail(f"{key} differs between protocol and rollout status")

    state = status.get("status")
    if state == "pending":
        if not status.get("expected_model") or not status.get("expected_upstream_model"):
            fail("pending status needs exact model and upstream route metadata")
        if (
            status.get("latest_matching_campaign") is not None
            or status.get("latest_matching_campaigns")
        ):
            fail("pending status must not name a matching campaign")
        if args.require_confirmed:
            fail("current environment still needs a matching AxonHub rollout")
        print("live rollout status: pending (metadata consistent)")
        return
    if state != "confirmed":
        fail(f"unknown status {state!r}")

    campaigns = status.get("latest_matching_campaigns")
    if not isinstance(campaigns, list) or not campaigns:
        campaign = status.get("latest_matching_campaign")
        campaigns = [campaign] if isinstance(campaign, dict) else []
    if not campaigns:
        fail("confirmed status needs matching campaign metadata")

    expected_model = status.get("expected_model")
    expected_upstream = status.get("expected_upstream_model")
    if not expected_model or not expected_upstream:
        fail("confirmed status needs exact model and upstream route metadata")
    expected_models = {expected_model}
    observed_models = {campaign.get("model") for campaign in campaigns}
    if observed_models != expected_models:
        printable = sorted(str(model) for model in observed_models)
        fail(f"confirmed iteration models differ: {printable}")

    for campaign in campaigns:
        if campaign.get("trace_reviewed") is not True:
            fail("confirmed campaign has not been marked trace-reviewed")
        if campaign.get("provider") != "AxonHub":
            fail("live validation must use AxonHub")
        if campaign.get("atif_native_continuity") is not True:
            fail("confirmed campaign lacks native ATIF continuity")
        evidence_digest = campaign.get("evidence_manifest_sha256", "")
        if re.fullmatch(r"[0-9a-f]{64}", evidence_digest) is None:
            fail("confirmed campaign lacks an anchored evidence-manifest digest")

        registration_path = ROOT / campaign.get("registration", "")
        report_path = ROOT / campaign.get("report", "")
        if not registration_path.is_file():
            fail("matching registration is missing")
        if not report_path.is_file():
            fail("matching reviewed report is missing")
        registration = load(registration_path)
        report = load(report_path)
        if report.get("evidence_manifest_sha256") != evidence_digest:
            fail("reviewed report does not match the anchored evidence manifest")
        if registration.get("input_revision") != status["input_revision"]:
            fail("registration input revision is stale")
        if registration.get("phase1_gate_revision") != status["phase1_gate_revision"]:
            fail("registration Phase 1 gate revision is stale")
        if registration.get("outcome_revision") != status["outcome_revision"]:
            fail("registration outcome revision is stale")
        if campaign.get("model") not in registration.get("models", {}).values():
            fail("campaign model does not match its frozen registration")
        if set(registration.get("upstream_models", {}).values()) != {expected_upstream}:
            fail("campaign upstream route does not match status metadata")
        registered_hashes = registration.get("code_hashes", {})
        missing = sorted(LIVE_EXECUTION_PATHS - registered_hashes.keys())
        if missing:
            fail("registration lacks live execution hashes: " + ", ".join(missing))
        for relative in sorted(LIVE_EXECUTION_PATHS):
            expected = registered_hashes[relative]
            path = ROOT / relative
            if not path.is_file() or digest(path) != expected:
                fail(f"live-validated source changed: {relative}")
    print("live rollout status: current campaign confirmed and source hashes match")


if __name__ == "__main__":
    main()
