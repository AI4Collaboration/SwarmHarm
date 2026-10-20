#!/usr/bin/env python3
"""Small paired Luna effort diagnostic; no adaptive retries or extensions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def fleet():
    spec = importlib.util.spec_from_file_location("luna_factor_fleet", REPO / "experiments/hf-fleet-v2/run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prepare(root):
    raise ValueError("The historical effort-coaching comparison is retired. Use a neutral current runner; archived trials retain their frozen source.")


def collect(root):
    runner = fleet()
    study = runner.load(root / "study.json")
    assert runner.sha(root / "study.json") == runner.load(root / "study-seal.json")["sha256"]
    assert runner.sha(__file__) == study["runner_sha256"]
    with (root / "started.json").open("x") as stream:
        json.dump({"at": runner.utc()}, stream)
    outcomes = []
    for arm in study["arms"]:
        output = root / arm["profile"]
        assert runner.sha(output / "registration.json") == arm["registration_sha256"]
        runner.ACTIVE_OUTPUT = output
        reg = runner.frozen(output)
        runner.transport.MODEL = runner.legacy.MODEL = reg["model"]
        row = {"arm": arm["profile"], "started_at": runner.utc()}
        outcomes.append(row)
        runner.save(root / "progress.json", outcomes)
        try:
            runner.legacy.preflight(output)
            row["preflight"] = "passed"
            with ThreadPoolExecutor(max_workers=1) as providers:
                runner.run_world(output, reg["calibration"], reg, providers)
                if not runner.gate(output, reg):
                    row["status"] = "calibration_failed"
                else:
                    row["calibration"] = "passed"
                    runner.save(output / "natural-started.json", {"at": runner.utc(), "gate_sha256": runner.sha(output / "gate.json")})
                    states = runner.run_world(output, reg["cells"][0], reg, providers)
                    row["actor_statuses"] = states
                    row["status"] = "collected"
                    runner.save(output / "cleanup-summary.json", {"finished_at": runner.utc(),
                        "owned_provider_futures_complete": True, "new_credentials_or_cloud_resources": 0,
                        "hosted_runtime_changed": False})
            if row["status"] == "collected":
                for script in ("hf-fleet-v2/review.py", "hf-method-analysis/policy_exposure.py",
                               "hf-method-analysis/handoff.py", "hf-method-analysis/output_quality.py"):
                    proc = subprocess.run([sys.executable, str(REPO / "experiments" / script), "--output", str(output)],
                                          cwd=REPO, text=True, capture_output=True)
                    runner.save(output / (Path(script).stem + "-execution.json"),
                                {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
                    if proc.returncode:
                        row.setdefault("review_errors", []).append(script)
                row["status"] = "review_failed" if row.get("review_errors") else "reviewed"
        except Exception as exc:
            row.update(status="collection_error", error_type=type(exc).__name__, error=str(exc))
        row["finished_at"] = runner.utc()
        runner.save(root / "progress.json", outcomes)
        print(json.dumps(row), flush=True)
    runner.save(root / "completion.json", {"at": runner.utc(), "outcomes": outcomes, "no_retry": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "collect"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    {"prepare": prepare, "collect": collect}[args.phase](args.output.resolve())
