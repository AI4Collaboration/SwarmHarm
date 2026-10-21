#!/usr/bin/env python3
"""Fixed neutral-prompt model coverage using the existing contained fleet."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MODELS = ("gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra", "gpt-6-sol",
          "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
CHANNELS = ("no_channel", "side_channel", "legal_channel")
MODES = ("all_blocked", "mixed")


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def fleet():
    path = REPO / "experiments/hf-fleet-v2/run.py"
    spec = importlib.util.spec_from_file_location("coverage_fleet", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def prepare(root):
    cache = load(Path.home() / ".codex/models_cache.json")
    available = {m["slug"] for m in cache["models"]
                 if m.get("visibility") == "list" and m.get("supported_in_api")}
    if not set(MODELS) <= available:
        raise ValueError("A registered model is missing from the current local model catalog")
    root.mkdir(parents=True, exist_ok=False)
    runner = fleet()
    cells = []
    for model in MODELS:
        for closed in (False, True):
            output = root / model / ("closed" if closed else "open")
            runner.prepare(output, "neutral", list(CHANNELS), list(MODES), closed,
                           "neutral-model-coverage-2026-10-19", model, 1)
            cells.append({"model": model, "weakness_open": not closed,
                          "path": str(output.relative_to(root)),
                          "registration_sha256": sha(output / "registration.json")})
    registration = {"created_at": utc(), "models": list(MODELS), "runs": cells,
        "profile": "neutral", "reasoning": runner.EFFORT,
        "channels": list(CHANNELS), "source_access_patterns": list(MODES),
        "worlds_per_model": 12, "independent_repetitions_per_cell": 1,
        "source": "Existing MiMo-derived healthcare and accounting fleet fixtures",
        "prompt_policy": "Unchanged original business tasks and neutral system instruction; no pressure, method seeds or collaboration instructions",
        "gates": "Each registered run must pass a native two-request tool round-trip and four authorized task calibrations before its natural worlds",
        "failure_policy": "No retries or replacement of failed trajectories; a failed gate excludes that run from natural collection",
        "scope_limit": "This covers the declared grid only; one world per cell does not estimate general rates or establish causality",
        "catalog_fetched_at": cache.get("fetched_at"),
        "unconfigured_models": ["Haiku", "DeepSeek", "GLM"],
        "unconfigured_reason": "No current local provider credentials or verified route; no infrastructure provisioning",
        "controller_sha256": sha(__file__)}
    save(root / "batch.json", registration)
    save(root / "batch-seal.json", {"sha256": sha(root / "batch.json")})
    print(json.dumps({"prepared": True, "models": len(MODELS), "worlds": len(cells) * 6}), flush=True)


def run_one(root, model):
    batch = load(root / "batch.json")
    assert sha(root / "batch.json") == load(root / "batch-seal.json")["sha256"]
    assert sha(__file__) == batch["controller_sha256"]
    assert model in batch["models"]
    runner = fleet()
    summary = {"model": model, "started_at": utc(), "runs": []}
    for registered in (x for x in batch["runs"] if x["model"] == model):
        output = root / registered["path"]
        assert sha(output / "registration.json") == registered["registration_sha256"]
        runner.ACTIVE_OUTPUT = output
        reg = runner.frozen(output)
        runner.transport.MODEL = runner.legacy.MODEL = model
        row = {"path": registered["path"], "weakness_open": registered["weakness_open"]}
        summary["runs"].append(row)
        # If the open run cannot pass the route gate, do not hammer the same
        # route for the closed run. The missing arm remains explicitly unrun.
        if summary["runs"][0].get("status") == "preflight_failed" and len(summary["runs"]) > 1:
            row.update(status="not_run", reason="same_model_route_gate_failed")
            save(output / "not-run.json", row)
            continue
        try:
            runner.legacy.preflight(output)
            row["preflight"] = "passed"
        except Exception as exc:
            row.update(status="preflight_failed", error=str(exc), error_type=type(exc).__name__)
            save(output / "preflight-failure.json", row)
            save(root / model / "result.json", summary)
            continue
        try:
            with ThreadPoolExecutor(max_workers=1) as providers:
                runner.run_world(output, reg["calibration"], reg, providers)
                if not runner.gate(output, reg):
                    row.update(status="calibration_failed")
                else:
                    row["calibration"] = "passed"
                    save(output / "natural-started.json", {"at": utc(), "gate_sha256": sha(output / "gate.json")})
                    # Serialized worlds keep all models under identical load.
                    for cell in reg["cells"]:
                        runner.run_world(output, cell, reg, providers)
                    save(output / "cleanup-summary.json", {"finished_at": utc(),
                        "owned_provider_futures_complete": True,
                        "new_credentials_or_cloud_resources": 0, "hosted_runtime_changed": False})
                    row["status"] = "collected"
            if row["status"] == "collected":
                for script in ("hf-fleet-v2/review.py", "hf-method-analysis/policy_exposure.py",
                               "hf-method-analysis/handoff.py", "hf-method-analysis/output_quality.py"):
                    result = subprocess.run([sys.executable, str(REPO / "experiments" / script),
                        "--output", str(output)], cwd=REPO, capture_output=True, text=True)
                    save(output / (Path(script).stem + "-execution.json"),
                         {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
                    if result.returncode:
                        row.setdefault("review_errors", []).append(script)
                row["status"] = "review_failed" if row.get("review_errors") else "reviewed"
        except Exception as exc:
            row.update(status="collection_error", error=str(exc), error_type=type(exc).__name__)
        save(root / model / "result.json", summary)
        print(json.dumps(row), flush=True)
    summary["finished_at"] = utc()
    save(root / model / "result.json", summary)


def collect(root):
    batch = load(root / "batch.json")
    assert sha(root / "batch.json") == load(root / "batch-seal.json")["sha256"]
    results = []
    for model in batch["models"]:
        output = root / model
        with (output / "controller.log").open("x") as log:
            proc = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                "--phase", "one-model", "--output", str(root), "--model", model],
                stdout=log, stderr=subprocess.STDOUT, cwd=REPO)
        result = load(output / "result.json") if (output / "result.json").exists() else {
            "model": model, "status": "controller_failed", "exit_code": proc.returncode}
        results.append(result)
        save(root / "results.json", results)
        print(json.dumps(result), flush=True)
    save(root / "completion.json", {"finished_at": utc(), "models_attempted": len(results),
        "no_retry": True, "new_credentials_or_cloud_resources": 0})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=("prepare", "collect", "one-model"), required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", choices=MODELS)
    args = p.parse_args()
    root = args.output.resolve()
    if args.phase == "prepare":
        prepare(root)
    elif args.phase == "collect":
        collect(root)
    else:
        run_one(root, args.model)


if __name__ == "__main__":
    main()
