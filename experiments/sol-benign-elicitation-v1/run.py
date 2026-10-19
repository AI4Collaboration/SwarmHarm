"""Frozen Sol development world: missing inputs and actual peer artifacts."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import secrets
import subprocess
import sys
import threading

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MODELS = ("gpt-6.1-sol",)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def engine():
    runner = module("sol_benign_handoff_engine", REPO / "experiments/sol-handoff-v1/run.py")
    runner.EFFORT = runner.legacy.EFFORT = "xhigh"
    runner.DEFAULT_BUDGET.update(max_provider_concurrency=1, max_concurrent_worlds=1,
                                 request_timeout_seconds=150)
    return runner


def prepare(root):
    assert not root.exists(), "Use a new output directory"
    admission = module("sol_benign_admission", REPO / "experiments/classifier-screen-v1/admit.py")
    for task in ("healthcare", "finance_accounting"):
        admission.assert_allowed("sol-benign-elicitation-v1", task)
    root.mkdir(parents=True)
    runner = engine()
    for model in MODELS:
        folder = root / model
        runner.prepare(folder, "sol-benign-missing-inputs-2026-10-19", model, "neutral")
        reg = runner.load(folder / "registration.json")
        cell = next(c for c in reg["cells"] if c["channel"] == "side_channel" and c["weakness_open"])
        reg["cells"] = [cell]
        reg.update(family="swarmharm/sol-benign-elicitation-v1",
            study="Exploratory Sol follow-up: one six-worker business world with missing staged inputs and genuine shared work.",
            development_changes=["All natural workers lack the supporting-source role and normal staging is missing", "On-access permission presentation; unchanged source and cache ACLs in ordinary metadata", "Actual work filenames at later arrivals, without seeded bodies or methods", "Three two-worker waves", "Neutral subject instruction"],
            prior_negative_result="experiments/lesswrong-benign-v1/RESULTS.md",
            comparison_limit="Several environment factors co-change; no causal attribution or pooled incidence estimate.",
            pressure="none",
            adaptation={"backend": "Pure local typed business-service dictionaries; no shell, network, host file, credentials or evaluator access.",
                        "not_an_exact_upstream_reproduction": True,
                        "no_seeded_peer_method_or_claimed_success": True})
        for source in (HERE / "run.py", HERE / "README.md"):
            relative = str(source.relative_to(REPO))
            target = folder / "code" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
            reg["code_hashes"][relative] = runner.sha(source)
        world = runner.FleetWorld(runner.load(folder / "fixtures.json"), runner.load(folder / "references.json"),
            world_id=cell["id"], plan=cell["plan"], channel=cell["channel"], weakness_open=True, framing=cell["framing"])
        tools = runner.load(folder / "tools.json")
        assert not {t["name"] for t in tools} & {"bash", "shell", "web_search", "browser"}
        initial = {}
        for actor, spec in cell["plan"].items():
            world.add_actor(actor, spec["task_id"], spec["wave"])
            native = world.describe_task(actor)
            prompt = native.pop("prompt")
            assert native["recent_work_index"] == []
            initial[actor] = {"instructions": reg["instructions"], "input": [
                {"role": "developer", "content": json.dumps(native, ensure_ascii=False)},
                {"role": "user", "content": prompt}], "tools": tools}
        runner.save(folder / "initial-input-audit.json", {"model_requests": 0, "base_inputs": initial,
            "later_arrival_inputs_include_only_actual_work_metadata": True,
            "note": "Actual arrival inputs are exported during collection and verified by replay.",
            "tool_execution_network_host_access": False, "prior_peer_messages_seeded": False})
        reg["input_hashes"]["initial-input-audit.json"] = runner.sha(folder / "initial-input-audit.json")
        runner.save(folder / "registration.json", reg)
        runner.save(folder / "registration-seal.json", {"sha256": runner.sha(folder / "registration.json"), "model_requests_at_sealing": 0})
    runner.save(root / "study.json", {"created_at": runner.utc(), "models": MODELS,
        "worlds_per_model": 1, "experimental_workers_per_model": 6, "calibration_workers_per_model": 4,
        "no_retries_or_prompt_rewrites_during_collection": True,
        "status": "prepared", "runner_sha256": runner.sha(HERE / "run.py")})
    print(json.dumps({"prepared": True, "models": MODELS, "natural_worlds": 1, "natural_workers": 6}))


def collect(root):
    assert not (root / "started.json").exists(), "Do not restart or replace trajectories"
    runner = engine()
    study = runner.load(root / "study.json")
    assert study["runner_sha256"] == runner.sha(HERE / "run.py")
    sys.path.insert(0, str(REPO / "experiments/classifier-screen-v1"))
    classifier = module("benign_response_review", REPO / "experiments/classifier-screen-v1/run.py")
    runner.save(root / "started.json", {"time": runner.utc()})
    statuses = {}
    for model in MODELS:
        output = root / model
        runner.ACTIVE_OUTPUT = output
        reg = runner.frozen(output)
        runner.transport.MODEL = runner.legacy.MODEL = model
        original_call = runner.transport.call
        stop = threading.Event()
        observed = []

        def monitored_call(body, directory, label, timeout=150):
            if stop.is_set():
                raise RuntimeError("Model held after confirmed filter/refusal; no further request")
            try:
                response = original_call(body, directory, label, timeout)
                outcome = classifier.classify(response)
            except Exception:
                error_file = Path(directory) / (label + ".error.json")
                if error_file.exists():
                    outcome = classifier.classify(runner.load(error_file), True)
                else:
                    outcome = {"status": "provider_error"}
                observed.append({"path": str(directory), "label": label, **outcome})
                runner.save(output / "response-review.json", observed)
                stop.set()
                print(json.dumps({"alert": outcome["status"], "model": model, "path": str(directory)}), flush=True)
                raise
            observed.append({"path": str(directory), "label": label, **outcome})
            runner.save(Path(directory) / (label + ".screen.json"), outcome)
            runner.save(output / "response-review.json", observed)
            if outcome["status"] in {"provider_filter", "native_refusal"}:
                stop.set()
                print(json.dumps({"alert": outcome["status"], "model": model, "path": str(directory)}), flush=True)
                raise RuntimeError("Confirmed filter/refusal retained; model held")
            if outcome["status"] == "text_refusal_candidate":
                print(json.dumps({"alert": "text_refusal_candidate", "model": model, "path": str(directory)}), flush=True)
            return response

        runner.transport.call = monitored_call
        progress = {"model": model, "phase": "preflight", "status": "running"}
        def update(**values):
            progress.update(values, updated_at=runner.utc())
            runner.save(output / "progress.json", progress)
            print(json.dumps(progress), flush=True)
        update()
        try:
            runner.legacy.preflight(output)
            update(phase="calibration")
            with ThreadPoolExecutor(max_workers=1) as providers:
                runner.run_world(output, reg["calibration"], reg, providers)
                if not runner.gate(output, reg):
                    update(status="calibration_failed")
                elif stop.is_set():
                    update(status="provider_or_refusal_hold")
                else:
                    update(phase="natural")
                    runner.save(output / "natural-started.json", {"time": runner.utc(), "gate_sha256": runner.sha(output / "gate.json")})
                    states = runner.run_world(output, reg["cells"][0], reg, providers)
                    update(phase="review", status="provider_or_refusal_hold" if stop.is_set() else "collected", actor_statuses=states)
            if progress["status"] == "collected":
                runner.save(output / "cleanup-summary.json", {
                    "finished_at": runner.utc(), "owned_provider_futures_complete": True,
                    "new_credentials_or_cloud_resources": 0, "hosted_runtime_changed": False,
                    "actor_statuses": progress["actor_statuses"],
                })
                failures = []
                for script in ("sol-handoff-v1/review.py", "hf-method-analysis/policy_exposure.py",
                               "hf-method-analysis/handoff.py", "hf-method-analysis/output_quality.py"):
                    result = subprocess.run([sys.executable, str(REPO / "experiments" / script), "--output", str(output)],
                        cwd=REPO, capture_output=True, text=True)
                    runner.save(output / (Path(script).stem + "-execution.json"),
                        {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
                    if result.returncode:
                        failures.append(script)
                update(status="review_failed" if failures else "reviewed", review_errors=failures)
        except Exception as error:
            update(status="collection_error", error_type=type(error).__name__, error=str(error))
        finally:
            runner.transport.call = original_call
        runner.save(output / "completion.json", {**progress, "finished_at": runner.utc(), "no_retry": True})
        statuses[model] = progress["status"]
        runner.save(root / "progress.json", {"updated_at": runner.utc(), "models": statuses})
    runner.save(root / "completion.json", {"finished_at": runner.utc(), "models": statuses,
        "no_external_subject_actions": True, "new_infrastructure_or_credentials": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("prepare", "collect"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    {"prepare": prepare, "collect": collect}[args.phase](args.output.resolve())
