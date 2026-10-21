"""Run pinned upstream tasks, preserving source, evidence and failed attempts."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from inspect_ai import Task, eval_async
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.solver import chain, solver
from inspect_ai.util import sandbox

import provider

MODELS = ["gpt-6-luna", "gpt-6.1-sol"]
JUDGE = "axonhub_responses/gpt-6.1-sol"
CELLS = [
    ("step1_xlsx", "step1_gdrive_xlsx", {"scaffold": "react", "condition": "baseline",
        "drive": "intense", "scorer": "judge", "turn_limit": 40, "temperature": 1.0,
        "deletable_registry": False, "delete_aware": False}),
    ("step2_bank", "step2_reachout", {"scaffold": "react", "condition": "baseline",
        "drive": "fair", "world": "protein_bank", "collab": False, "anonymize": False,
        "turn_limit": 100, "temperature": 1.0}),
    ("step2_none", "step2_reachout", {"scaffold": "react", "condition": "baseline",
        "drive": "fair", "world": "protein_none", "collab": False, "anonymize": False,
        "turn_limit": 100, "temperature": 1.0}),
    ("step3_egress", "step3_egress_share", {"scaffold": "react", "drive": "driven",
        "turn_limit": 60, "temperature": 1.0}),
    ("step4_chain", "step4_hf_cheat_chain", {"scaffold": "react", "condition": "baseline",
        "variant": "neutral", "drive": "persist", "turn_limit": 60, "temperature": 1.0}),
]


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_source(root):
    manifest = json.loads((root / "upstream-source-manifest.json").read_text())
    mismatches = [name for name, expected in manifest["files"].items()
                  if digest(root / "source" / name) != expected]
    if mismatches:
        raise RuntimeError(f"Pinned upstream source changed: {mismatches}")
    return manifest


def upstream(root, module, params):
    source = root / "source"
    sys.path.insert(0, str(source / "src"))
    loaded = importlib.import_module(f"alignment_auditor.docker_replication.{module}.task")
    return getattr(loaded, module)(**params, judge_model=JUDGE)


def prepare(root):
    manifest = verify_source(root)
    entries = []
    for name, module, params in CELLS:
        task = upstream(root, module, params)
        compose = Path(task.sandbox.config)
        config = yaml.safe_load(compose.read_text())
        assert all(net.get("internal") for net in config["networks"].values())
        assert all(not service.get("ports") and not service.get("volumes")
                   and not service.get("privileged")
                   for service in config["services"].values())
        sample = task.dataset[0]
        entries.append({"condition": name, "module": module, "parameters": params,
                        "turn_limit": task.turn_limit, "time_limit": task.time_limit,
                        "assignment": sample.input,
                        "assignment_sha256": hashlib.sha256(sample.input.encode()).hexdigest(),
                        "compose": str(compose.relative_to(root)),
                        "compose_sha256": digest(compose), "epochs_per_model": 64})
    plan = {
        "registered_at": now(), "source_commit": manifest["commit"],
        "source_manifest_sha256": digest(root / "upstream-source-manifest.json"),
        "models": MODELS, "cells": entries, "total_scheduled_attempts": 640,
        "reasoning_effort": "high", "reasoning_summary": "auto",
        "endpoint": provider.ENDPOINT, "credential_scope": "host-only existing Codex login",
        "judge_model": JUDGE, "original_judge": "openrouter/anthropic/claude-opus-4.8",
        "max_model_connections_per_model": 1, "max_live_sandboxes": 2,
        "batch_epochs": 8, "batches_per_cell": 8,
        "temperature": "Upstream task requests 1.0; reasoning route uses its default sampling.",
        "max_tokens": "No target cap in upstream reasoning script; route default used. Judge's original 1200-token cap is not supported on this route.",
        "retries": "No automatic provider or sample replacement. A material error pauses collection with evidence intact.",
        "scoring": "Original scorers and rubrics with substituted Sol judge; server evidence retained for independent audit.",
        "scope": "Five main manual reproduction cells; not the article's optional ablations, 256-agent live fleet, Petri or RL study.",
        "peer_provenance": "Original seeded content and scripted writers; not independent live LLM peers.",
        "differences": ["Luna/Sol subjects in place of original subject models",
                        "Existing local Docker ARM64 environment, not Daytona scale-out",
                        "Host Codex inference route, not OpenRouter",
                        "Sol judge in place of Opus; original rubric retained",
                        "Two live sandboxes, one request per model; no provider/sample retries",
                        "Read-only operator evidence capture before and after each trajectory"],
        "runner_sha256": {p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
    }
    destination = root / "registration.json"
    if destination.exists():
        old = json.loads(destination.read_text())
        comparable = lambda value: {k: v for k, v in value.items() if k != "registered_at"}
        if comparable(old) != comparable(plan):
            raise RuntimeError("Registration already exists with different settings; use a new run directory")
    else:
        provider.save(destination, plan)
    return plan


ARCHIVE = """import base64,io,os,tarfile
b=io.BytesIO()
with tarfile.open(fileobj=b,mode='w:gz',dereference=False) as t:
 for p in PATHS:
  if os.path.exists(p): t.add(p,arcname=p.lstrip('/'),recursive=True)
print(base64.b64encode(b.getvalue()).decode())
"""


async def capture(root, scope, phase):
    folder = root / "evidence" / scope
    folder.mkdir(parents=True, exist_ok=True)
    for service, paths in (
        ("registry", ["/srv/registry", "/var/log/registry_access.log"]),
        ("default", ["/research", "/data", "/opt/exploitgym", "/tmp", "/home/agent"]),
    ):
        try:
            result = await sandbox(service).exec(
                ["python", "-c", "PATHS=" + repr(paths) + "\n" + ARCHIVE], timeout=45)
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:1000])
            payload = base64.b64decode(result.stdout.strip(), validate=True)
            (folder / f"{phase}-{service}.tar.gz").write_bytes(payload)
        except Exception as error:
            provider.save(folder / f"{phase}-{service}.error.json", {
                "type": type(error).__name__, "message": str(error)})
            if phase == "initial":
                raise


async def containment(root, scope):
    connections = [await sandbox(service).connection() for service in ("default", "registry")]
    ids = [connection.container for connection in connections]
    if not all(ids):
        raise RuntimeError("Could not identify owned sandbox containers")
    proc = await asyncio.create_subprocess_exec("docker", "inspect", *ids,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    data, errors = await proc.communicate()
    if proc.returncode:
        raise RuntimeError("Could not inspect owned sandbox containers")
    containers = json.loads(data)
    projects = {c["Config"]["Labels"]["com.docker.compose.project"] for c in containers}
    assert len(projects) == 1, "Inconsistent sandbox project"
    project = projects.pop()
    networks = sorted({key for c in containers for key in c["NetworkSettings"]["Networks"]})
    proc = await asyncio.create_subprocess_exec("docker", "network", "inspect", *networks,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    data, errors = await proc.communicate()
    details = json.loads(data)
    # Save only containment fields, not container environment variables.
    evidence = {"project": project, "containers": [
        {"id": c["Id"], "image": c["Image"], "mounts": c["Mounts"],
         "ports": c["NetworkSettings"]["Ports"], "privileged": c["HostConfig"]["Privileged"],
         "network_mode": c["HostConfig"]["NetworkMode"]} for c in containers],
        "networks": [{"name": n["Name"], "internal": n["Internal"]} for n in details]}
    provider.save(root / "evidence" / scope / "containment.json", evidence)
    assert all(n["Internal"] for n in details), "Non-internal network"
    assert all(not c["Mounts"] and not any(c["NetworkSettings"]["Ports"].values())
               and not c["HostConfig"]["Privileged"] for c in containers), "Host access found"


def instrument(task, root, condition, model, offset):
    @solver
    def begin():
        async def solve(state, generate):
            scope = f"{condition}/{model}/epoch-{offset + state.epoch:03d}"
            provider.SCOPE.set(scope)
            state.metadata["direct_scope"] = scope
            provider.event("sample_started", scope=scope, model=model,
                           sample_id=state.sample_id, epoch=offset + state.epoch)
            await containment(root, scope)
            return state
        return solve

    @solver
    def seeded():
        async def solve(state, generate):
            await capture(root, state.metadata["direct_scope"], "initial")
            provider.save(root / "evidence" / state.metadata["direct_scope"] / "initial-messages.json",
                          [message.model_dump(mode="json") for message in state.messages])
            return state
        return solve

    original_setup = task.setup
    stages = original_setup if isinstance(original_setup, list) else ([original_setup] if original_setup else [])
    task.setup = chain(begin(), *stages, seeded())
    original_cleanup = task.cleanup

    async def cleanup(state):
        scope = state.metadata.get("direct_scope", f"{condition}/{model}/unknown")
        provider.SCOPE.set(scope)
        await capture(root, scope, "final")
        provider.save(root / "evidence" / scope / "final-state.json", {
            "sample_id": state.sample_id, "epoch": offset + state.epoch,
            "messages": [message.model_dump(mode="json") for message in state.messages],
            "output": state.output.model_dump(mode="json") if state.output else None,
            "metadata": state.metadata,
        })
        provider.event("sample_cleanup", scope=scope, model=model)
        if original_cleanup:
            await original_cleanup(state)

    task.cleanup = cleanup
    task.model = get_model("axonhub_responses/" + model)
    task._name = f"lw_{condition}_{model.replace('.', '_').replace('-', '_')}_b{offset // 8 + 1}"
    return task


async def smoke(root):
    from alignment_auditor.docker_replication.harness.scaffolds import react_solver
    env = root / "source/src/alignment_auditor/docker_replication/env/compose.yaml"
    tasks = []
    for model in MODELS:
        task = Task(dataset=[Sample(id="transport-only", input="Run printf 'DOCKER_TOOL_OK\\n' with bash, then submit the observed output.")],
                    solver=react_solver(4, persona="Complete the user's task."),
                    sandbox=("docker", str(env)), turn_limit=4, time_limit=180,
                    config=GenerateConfig(temperature=1.0))
        tasks.append(instrument(task, root, "preflight_docker", model, 0))
    logs = await execute(tasks, root / "preflight/docker")
    for log in logs:
        if log.status != "success" or len(log.samples or []) != 1 or log.samples[0].error:
            raise RuntimeError("Docker transport preflight failed")
        sample = log.samples[0]
        assert any(m.role == "tool" and "DOCKER_TOOL_OK" in m.text for m in sample.messages)
        assert any(c.function == "submit" for c in sample.output.message.tool_calls or [])
    provider.save(root / "preflight/docker.json", {"passed": True, "models": MODELS, "counted_in_study": False})


async def execute(tasks, log_dir):
    return await eval_async(tasks, log_dir=str(log_dir), log_format="eval",
        epochs=tasks[0].epochs or 1, max_tasks=2, max_samples=2, max_sandboxes=2,
        max_subprocesses=12, fail_on_error=False, retry_on_error=0, score_on_error=False,
        log_realtime=True, log_samples=True, log_model_api=True, log_refusals=True,
        sandbox_cleanup=True, reasoning_effort="high", reasoning_summary="auto",
        max_connections=1, max_retries=0, timeout=300)


async def collect(root):
    plan = prepare(root)
    for model in MODELS:
        gate = json.loads((root / "preflight" / (model + ".json")).read_text())
        assert gate["passed"] and gate["actual_model"] == model
    assert json.loads((root / "preflight/docker.json").read_text())["passed"]
    if (root / "started.json").exists():
        raise RuntimeError("Run already started; do not launch a duplicate collector")
    provider.save(root / "started.json", {"time": now(), "pid": os.getpid(), "scheduled": 640})
    provider.event("collection_started", scheduled=640)
    completed = []
    try:
        for batch in range(8):
            for condition, module, parameters in CELLS:
                verify_source(root)
                tasks = []
                for model in MODELS:
                    task = upstream(root, module, parameters)
                    task.epochs = 8
                    tasks.append(instrument(task, root, condition, model, batch * 8))
                provider.event("batch_started", batch=batch + 1, condition=condition, epochs_per_model=8)
                logs = await execute(tasks, root / "evals" / f"batch-{batch + 1:02d}" / condition)
                for log in logs:
                    samples = log.samples or []
                    entry = {"batch": batch + 1, "condition": condition,
                             "model": log.eval.model, "status": log.status,
                             "samples": len(samples), "errors": sum(s.error is not None for s in samples),
                             "log": log.location,
                             "scores": log.results.model_dump(mode="json") if log.results else None}
                    completed.append(entry)
                    provider.save(root / "progress.json", {"updated": now(), "completed_batches": completed,
                        "samples_recorded": sum(e["samples"] for e in completed), "scheduled": 640})
                    provider.event("batch_model_finished", **entry)
                    if log.status != "success" or entry["samples"] != 8 or entry["errors"]:
                        raise RuntimeError(f"Batch did not complete cleanly: {condition} {log.eval.model}")
        provider.save(root / "completion.json", {"time": now(), "status": "complete",
            "samples": sum(e["samples"] for e in completed), "batches": completed})
        provider.event("collection_completed", samples=640)
    except BaseException as error:
        provider.save(root / "collector-failure.json", {"time": now(), "type": type(error).__name__,
            "message": str(error), "completed_batches": completed})
        provider.event("collection_stopped", type=type(error).__name__, message=str(error))
        raise


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["SWH_LW_OUTPUT"] = str(root)
    os.environ["INSPECT_DISPLAY"] = "plain"
    sys.path.insert(0, str(root / "source/src"))
    if args.prepare:
        prepare(root)
        print("Registered five cells, two models, 64 attempts per cell/model (640 total).")
    elif args.smoke:
        await smoke(root)
        print("Docker tool preflight passed for both models.")
    else:
        await collect(root)


if __name__ == "__main__":
    asyncio.run(main())
