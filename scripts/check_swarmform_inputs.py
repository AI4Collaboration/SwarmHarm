#!/usr/bin/env python3
"""Check SwarmForm's active matrix index and run its implemented offline workload tests."""

from itertools import product
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs/live-rollout-status.json"
PACKAGE = ROOT / "experiments/swarmharm-v1"


def fail(message):
    raise SystemExit("SwarmForm input check failed: " + message)


def validate_active_matrix(status):
    matrix = status["matrix"]
    axes = (matrix["deployments"], matrix["encoding_opportunities"], matrix["domains"])
    if tuple(len(axis) for axis in axes) != (5, 5, 4) or any(len(set(axis)) != len(axis) for axis in axes):
        fail("SwarmForm needs five distinct deployments, five encoding opportunities and four domains")
    if set(matrix["domains"]) != {"Engineering", "Data Analysis", "Financial Analysis", "Knowledge Work"}:
        fail("SwarmForm domain catalog differs from the registered design")
    if status["research_study"] != "SwarmForm" or not (ROOT / status["decision_record"]).is_file():
        fail("active SwarmForm study plan is missing")
    if (status["population"] != 3 or status["current_harness"] != "codex"
            or set(status["current_models"]) != {"openai/gpt-5.6-sol", "openai/gpt-6.1-sol"}):
        fail("SwarmForm's matched pair needs three agents of one registered Sol model per rollout")
    if matrix["unlisted_cell_status"] != "open":
        fail("unreviewed matrix cells must remain open")
    for domain, evidence in matrix["offline_workload_checks"].items():
        if domain not in matrix["domains"] or not (ROOT / evidence).is_file():
            fail(f"missing workload check for {domain}")
    keys = {"/".join(cell) for cell in product(*axes)}
    if status["next_checkpoint"] is not None and status["next_checkpoint"] not in keys:
        fail("next checkpoint is outside the matrix")
    cells = matrix["cells"]
    for key, entry in cells.items():
        if key not in keys or entry["status"] not in {"admitted", "equivalent", "unsupported"}:
            fail(f"invalid matrix disposition: {key}")
        if not (ROOT / entry["evidence"]).is_file():
            fail(f"missing matrix disposition evidence: {key}")
        if entry["status"] == "equivalent":
            canonical = entry.get("canonical", "")
            if (cells.get(canonical, {}).get("status") != "admitted"
                    or key.rsplit("/", 1)[-1] != canonical.rsplit("/", 1)[-1]):
                fail(f"equivalent input needs an admitted canonical cell in the same domain: {key}")
    print(f"SwarmForm plan: {len(keys)} candidates; {len(keys) - len(cells)} open")


def main():
    status = json.loads(STATUS.read_text())
    validate_active_matrix(status)
    registrations = set(status["maintained_registrations"])
    for name in registrations:
        folder = (ROOT / name).resolve()
        if folder.parent != PACKAGE / "registrations":
            fail(f"registration is outside the retained input directory: {name}")
        reg = json.loads((folder / "registration.json").read_text())
        if reg.get("research_study") != "SwarmForm" or len(reg.get("plan", {}).get("natural", {})) != status["population"]:
            fail(f"registration does not match the active three-agent SwarmForm study: {name}")
    for rollout in status["active_rollouts"]:
        if rollout.get("registration") not in registrations:
            fail("active rollout has no matching SwarmForm registration")

    checks = status["matrix"]["offline_workload_checks"]
    sys.path.insert(0, str(PACKAGE))
    for domain, relative in checks.items():
        path = (ROOT / relative).resolve()
        if path.parent != PACKAGE / "tests" or not path.name.endswith("_checks.py"):
            fail(f"invalid workload test path for {domain}: {relative}")
        suite = unittest.defaultTestLoader.loadTestsFromName("tests." + path.stem)
        if not suite.countTestCases() or not unittest.TextTestRunner().run(suite).wasSuccessful():
            fail(f"offline workload checks failed for {domain}")
    print(f"Offline workloads checked: {len(checks)} of {len(status['matrix']['domains'])}. Model calls: 0.")


if __name__ == "__main__":
    main()
