#!/usr/bin/env python3
"""Archive independently authored adversarial controls before model collection."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new control receipt path")
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    source = json.loads((REPO / "data/hf-campaign-v1/offline-verification.json").read_text())
    paths = sorted(ROOT.glob("tests/*.py")) + [ROOT / "world.py", ROOT / "tools.json"]
    receipt = {"checked_at": datetime.now(timezone.utc).isoformat(),
               "passed": result.wasSuccessful() and source["status"] == "pass",
               "mechanism_tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "skipped": len(result.skipped), "source_checks": source["check_count"],
               "coverage": "24 suite/feasibility/weakness/channel cells and three source tasks; data, proxy, communication, isolation, counterfactual and replay controls",
               "test_kind": "Deliberately scripted operator functionality/adversarial controls, never spontaneous behavior",
               "model_requests": 0,
               "hashes": {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
               "dependencies": {p: importlib.metadata.version(p) for p in ["jsonschema", "openpyxl", "pypdf"]}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in ["passed", "mechanism_tests", "source_checks", "model_requests"]}))
    if not receipt["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
