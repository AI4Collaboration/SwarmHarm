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
    runner = fleet()
    root.mkdir(parents=True, exist_ok=False)
    cell_id = "fleet-" + secrets.token_hex(6)
    arms = []
    native_inputs = []
    for profile in ("neutral", "resourceful"):
        output = root / profile
        runner.prepare(output, profile, ["side_channel"], ["mixed"], False,
                       "luna-factor-pilot-2026-10-19", "gpt-6-luna", 1)
        reg = runner.load(output / "registration.json")
        cell = reg["cells"][0]
        cell.update(id=cell_id, waves=[0, 1])
        cell["plan"] = runner.actor_plan(cell)
        reg["study"] = "Paired exploratory effort-instruction diagnostic; one world per arm, no incidence or causal-effect estimate."
        reg["diagnostic_intervention"] = profile
        reg["independent_unit"] = "world; four workers per world, one world per instruction arm"
        reg["arrival"] = "Two arrivals at rounds 0/4, or earlier after all current actors finish. No reactivation."
        reg["budget"]["max_world_concurrency"] = 1
        for source in (Path(__file__).resolve(), HERE / "README.md"):
            relative = str(source.relative_to(REPO))
            dest = output / "code" / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
            reg["code_hashes"][relative] = runner.sha(source)
        runner.save(output / "registration.json", reg)
        runner.save(output / "registration-seal.json", {"sha256": runner.sha(output / "registration.json"), "model_requests_at_sealing": 0})
        fixtures, references = runner.load(output / "fixtures.json"), runner.load(output / "references.json")
        world = runner.FleetWorld(fixtures, references, world_id=cell_id, plan=cell["plan"],
                                  channel=cell["channel"], weakness_open=cell["weakness_open"])
        inputs = {}
        for actor, spec in cell["plan"].items():
            world.add_actor(actor, spec["task_id"], spec["wave"])
            inputs[actor] = world.describe_task(actor)
        native_inputs.append(inputs)
        arms.append({"profile": profile, "registration_sha256": runner.sha(output / "registration.json")})
    assert native_inputs[0] == native_inputs[1], "Subject task inputs differ between arms"
    first, second = (runner.load(root / profile / "registration.json") for profile in ("neutral", "resourceful"))
    for key in ("cells", "budget", "reasoning", "model", "calibration"):
        assert first[key] == second[key], key
    # The operator-only unittest log includes measured execution time.
    for filename in ("fixtures.json", "references.json", "tools.json"):
        assert first["input_hashes"][filename] == second["input_hashes"][filename], filename
    runner.save(root / "study.json", {"created_at": runner.utc(), "model": "gpt-6-luna", "arms": arms,
        "natural_workers_per_arm": 4, "single_assigned_difference": "instructions",
        "identical_native_inputs_verified": True, "order": ["neutral", "resourceful"],
        "adaptive_extension": False, "runner_sha256": runner.sha(__file__),
        "hypothesis": "The historical general-effort instruction may change investigation of the cache route.",
        "limitations": ["one world per arm", "stochastic requests and sequential arm order", "shorter than historical positive run",
                        "blocker, channel, vulnerability and peer-method effects are not independently manipulated"]})
    runner.save(root / "study-seal.json", {"sha256": runner.sha(root / "study.json")})
    print(json.dumps({"prepared": True, "arms": 2, "natural_workers": 8, "identical_native_inputs": True}), flush=True)


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
