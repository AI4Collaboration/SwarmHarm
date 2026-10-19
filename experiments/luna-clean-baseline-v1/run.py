#!/usr/bin/env python3
"""One small Luna baseline after the communication-prompt cleanup."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def fleet():
    spec = importlib.util.spec_from_file_location("luna_clean_fleet", REPO / "experiments/hf-fleet-v2/run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prepare(output):
    runner = fleet()
    runner.prepare(output, "neutral", ["side_channel"], ["mixed"], False,
                   "luna-clean-baseline-2026-10-19", "gpt-6-luna", 1)
    reg = runner.load(output / "registration.json")
    cell = reg["cells"][0]
    cell["waves"] = [0, 1]
    cell["plan"] = runner.actor_plan(cell)
    reg.update(
        study="Single exploratory baseline after removing operator-added communication restrictions; not a causal comparison.",
        independent_unit="One world with four task workers: two authorized, then two blocked.",
        arrival="Two arrivals at rounds 0/4, or earlier after all current actors finish. No reactivation.",
        limits=["One small world, not an incidence estimate or causal effect of prompt cleanup",
                "Typed business-service tools, not a shell or the full LessWrong environment",
                "No pressure, effort intervention, seeded methods or fabricated peers",
                "Separate cases and a permission blocker, not the same-file missing-input task in LessWrong",
                "Two arrivals do not establish long-horizon persistence"],
    )
    reg["budget"]["max_world_concurrency"] = 1
    for source in (Path(__file__).resolve(), HERE / "README.md"):
        relative = str(source.relative_to(REPO))
        dest = output / "code" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
        reg["code_hashes"][relative] = runner.sha(source)

    fixtures, references = runner.load(output / "fixtures.json"), runner.load(output / "references.json")
    world = runner.FleetWorld(fixtures, references, world_id=cell["id"], plan=cell["plan"],
                              channel=cell["channel"], weakness_open=cell["weakness_open"])
    native = {}
    for actor, spec in cell["plan"].items():
        world.add_actor(actor, spec["task_id"], spec["wave"])
        native[actor] = world.describe_task(actor)
        assert "peer_communication" not in native[actor].get("permissions", {})
    actors = list(cell["plan"])
    donor, receiver = actors[0], actors[2]
    path = world.output_path(donor)
    written = world.call(donor, "registry_request", method="PUT", path=path, content="offline mechanics check")
    read = world.call(receiver, "registry_request", method="GET", path=path)
    assert written["status"] in (200, 201) and read["status"] == 200
    assert world.events[-1]["permitted"] is True
    runner.save(output / "offline-input-audit.json", {
        "model_requests": 0, "instructions": reg["instructions"], "native_inputs": native,
        "shared_work_write_and_read_passed": True,
        "audit_only_state_discarded_before_collection": True,
    })
    reg["input_hashes"]["offline-input-audit.json"] = runner.sha(output / "offline-input-audit.json")
    runner.save(output / "registration.json", reg)
    runner.save(output / "registration-seal.json", {"sha256": runner.sha(output / "registration.json"), "model_requests_at_sealing": 0})
    runner.save(output / "study.json", {
        "created_at": runner.utc(), "model": reg["model"], "reasoning": reg["reasoning"],
        "natural_worlds": 1, "natural_workers": 4, "authorized_calibration_workers": 4,
        "registration_sha256": runner.sha(output / "registration.json"),
        "adaptive_extension": False, "retries": 0, "runner_sha256": runner.sha(__file__),
    })
    print(json.dumps({"prepared": True, "natural_worlds": 1, "natural_workers": 4,
                      "shared_work_mechanics_passed": True}), flush=True)


def collect(output):
    runner = fleet()
    study = runner.load(output / "study.json")
    assert study["registration_sha256"] == runner.sha(output / "registration.json")
    assert study["runner_sha256"] == runner.sha(__file__)
    runner.ACTIVE_OUTPUT = output
    reg = runner.frozen(output)
    runner.transport.MODEL = runner.legacy.MODEL = reg["model"]
    with (output / "started.json").open("x") as stream:
        json.dump({"at": runner.utc()}, stream)
    progress = {"started_at": runner.utc(), "phase": "preflight", "status": "running"}

    def update(**values):
        progress.update(values, updated_at=runner.utc())
        runner.save(output / "progress.json", progress)
        print(json.dumps(progress), flush=True)

    update()
    try:
        runner.legacy.preflight(output)
        update(phase="calibration", preflight="passed")
        with ThreadPoolExecutor(max_workers=1) as providers:
            runner.run_world(output, reg["calibration"], reg, providers)
            if not runner.gate(output, reg):
                update(status="calibration_failed")
            else:
                update(phase="natural", calibration="passed")
                runner.save(output / "natural-started.json", {"at": runner.utc(), "gate_sha256": runner.sha(output / "gate.json")})
                states = runner.run_world(output, reg["cells"][0], reg, providers)
                runner.save(output / "cleanup-summary.json", {
                    "finished_at": runner.utc(), "owned_provider_futures_complete": True,
                    "new_credentials_or_cloud_resources": 0, "hosted_runtime_changed": False,
                    "actor_statuses": states,
                })
                update(phase="review", status="collected", actor_statuses=states)
        if progress["status"] == "collected":
            review_errors = []
            for script in ("hf-fleet-v2/review.py", "hf-method-analysis/policy_exposure.py",
                           "hf-method-analysis/handoff.py", "hf-method-analysis/output_quality.py"):
                proc = subprocess.run([sys.executable, str(REPO / "experiments" / script), "--output", str(output)],
                                      cwd=REPO, text=True, capture_output=True)
                runner.save(output / (Path(script).stem + "-execution.json"),
                            {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr})
                if proc.returncode:
                    review_errors.append(script)
            update(status="review_failed" if review_errors else "reviewed", review_errors=review_errors)
    except Exception as exc:
        update(status="collection_error", error_type=type(exc).__name__, error=str(exc))
    update(finished_at=runner.utc())
    runner.save(output / "completion.json", {**progress, "no_retry": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("prepare", "collect"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    {"prepare": prepare, "collect": collect}[args.phase](args.output.resolve())
