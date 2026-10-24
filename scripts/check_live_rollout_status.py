#!/usr/bin/env python3
"""Reject stale live-validation claims for the maintained formation environment."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "docs/live-rollout-status.json"
PROTOCOL_PATH = ROOT / "experiments/swarm-formation-v20/protocol.json"


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
    for key in ("input_revision", "outcome_revision"):
        if status.get(key) != protocol.get(key):
            fail(f"{key} differs between protocol and rollout status")

    state = status.get("status")
    if state == "pending":
        if status.get("latest_matching_campaign") is not None:
            fail("pending status must not name a matching campaign")
        if args.require_confirmed:
            fail("current environment still needs a matching AxonHub rollout")
        print("live rollout status: pending (metadata consistent)")
        return
    if state != "confirmed":
        fail(f"unknown status {state!r}")

    campaign = status.get("latest_matching_campaign")
    if not isinstance(campaign, dict):
        fail("confirmed status needs latest_matching_campaign metadata")
    if campaign.get("trace_reviewed") is not True:
        fail("confirmed campaign has not been marked trace-reviewed")
    if campaign.get("provider") != "AxonHub":
        fail("live validation must use AxonHub")

    registration_path = ROOT / campaign.get("registration", "")
    report_path = ROOT / campaign.get("report", "")
    if not registration_path.is_file():
        fail("matching registration is missing")
    if not report_path.is_file():
        fail("matching reviewed report is missing")
    registration = load(registration_path)
    if registration.get("input_revision") != status["input_revision"]:
        fail("registration input revision is stale")
    if registration.get("outcome_revision") != status["outcome_revision"]:
        fail("registration outcome revision is stale")
    for relative, expected in registration.get("code_hashes", {}).items():
        path = ROOT / relative
        if not path.is_file() or digest(path) != expected:
            fail(f"live-validated source changed: {relative}")
    print("live rollout status: confirmed and source hashes match")


if __name__ == "__main__":
    main()
