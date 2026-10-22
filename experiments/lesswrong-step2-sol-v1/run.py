"""Reproduce the public LessWrong Step 2 bank/none experiment on GPT-5.6 Sol."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib
import json
import os
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from inspect_ai import Task, eval_async
from inspect_ai.dataset import Sample
from inspect_ai.model import (
    ChatMessageSystem,
    ChatMessageTool,
    ChatMessageUser,
    GenerateConfig,
    get_model,
)
from inspect_ai.solver import chain, solver
from inspect_ai.tool import ToolInfo, ToolParam, ToolParams
from inspect_ai.util import sandbox

import provider

MODEL = provider.MODEL
JUDGE = f"axonhub_step2/{MODEL}"
PARAMETERS = {
    "scaffold": "react",
    "condition": "baseline",
    "drive": "fair",
    "collab": False,
    "anonymize": False,
    "turn_limit": 100,
    "temperature": 1.0,
}
CELLS = ("protein_bank", "protein_none")
TARGET_PER_CELL = 64


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_source(root):
    manifest = json.loads((root / "upstream-source-manifest.json").read_text())
    mismatches = [
        name for name, expected in manifest["files"].items()
        if digest(root / "source" / name) != expected
    ]
    if mismatches:
        raise RuntimeError(f"Pinned upstream source changed: {mismatches}")
    return manifest


def source_task(root, world):
    source = root / "source"
    source_code = str(source / "src")
    if source_code not in sys.path:
        sys.path.insert(0, source_code)
    loaded = importlib.import_module(
        "alignment_auditor.docker_replication.step2_reachout.task"
    )
    return loaded.step2_reachout(**PARAMETERS, world=world, judge_model=JUDGE)


def prepare(root, parent):
    if (root / "started.json").exists():
        raise RuntimeError("Run already started; use a new output directory")
    root.mkdir(parents=True, exist_ok=True)
    parent = parent.resolve()
    if not (parent / "source").exists() or not (parent / "upstream-source-manifest.json").exists():
        raise RuntimeError("Pinned parent lacks source or source manifest")
    if not (root / "source").exists():
        (root / "source").symlink_to(parent / "source", target_is_directory=True)
    if (root / "source").resolve() != (parent / "source").resolve():
        raise RuntimeError("Output source points to a different snapshot")
    manifest_path = root / "upstream-source-manifest.json"
    if not manifest_path.exists():
        shutil.copyfile(parent / "upstream-source-manifest.json", manifest_path)
    manifest = verify_source(root)
    cells = []
    for world in CELLS:
        task = source_task(root, world)
        sample = task.dataset[0]
        compose = Path(task.sandbox.config)
        cells.append({
            "condition": world,
            "parameters": {**PARAMETERS, "world": world},
            "assignment": sample.input,
            "assignment_sha256": hashlib.sha256(sample.input.encode()).hexdigest(),
            "compose": "source/" + str(compose.relative_to((root / "source").resolve())),
            "compose_sha256": digest(compose),
            "turn_limit": task.turn_limit,
            "time_limit": task.time_limit,
            "scheduled": TARGET_PER_CELL,
        })
    plan = {
        "registered_at": now(),
        "objective": "Reproduce the public LessWrong Step 2 bank-versus-none reach-out comparison.",
        "source_commit": manifest["commit"],
        "source_manifest_sha256": digest(manifest_path),
        "model": MODEL,
        "model_route": "AxonHub Responses",
        "endpoint": provider.ENDPOINT,
        "judge_model": JUDGE,
        "cells": cells,
        "scheduled_attempts": TARGET_PER_CELL * len(CELLS),
        "reasoning_effort": "high",
        "reasoning_summary": "auto",
        "temperature": "Upstream task requests 1.0; the Responses reasoning route uses its supported defaults.",
        "collection_order": "Ordinal 1..64; protein_bank and protein_none paired at each ordinal.",
        "retries": "No provider or trajectory retry; errors are preserved and stop the affected collection.",
        "scope": "Exact public Step 2 task source and two published worlds only; this tests emergent reach-out, not misalignment or harm.",
        "differences_from_published_run": [
            "AxonHub replaces the paper's OpenRouter route.",
            "The original scoring rubric is retained but GPT-5.6 Sol replaces Claude Opus 4.8 as judge.",
            "Local Docker replaces Daytona; the task containers remain internally networked and unprivileged.",
            "Trials are paired sequentially rather than sharded across remote workers.",
        ],
        "runner_sha256": {
            p.name: digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))
        },
    }
    destination = root / "registration.json"
    if destination.exists():
        old = json.loads(destination.read_text())
        comparable = lambda value: {k: v for k, v in value.items() if k != "registered_at"}
        if comparable(old) != comparable(plan):
            raise RuntimeError("Registration differs; use a new output directory")
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
        result = await sandbox(service).exec(
            ["python", "-c", "PATHS=" + repr(paths) + "\n" + ARCHIVE], timeout=45
        )
        if result.returncode != 0:
            provider.save(folder / f"{phase}-{service}.error.json", {
                "returncode": result.returncode, "stderr": result.stderr[:1000]
            })
            raise RuntimeError(f"Could not capture {phase} {service} evidence")
        (folder / f"{phase}-{service}.tar.gz").write_bytes(
            base64.b64decode(result.stdout.strip(), validate=True)
        )


async def containment(root, scope):
    connections = [await sandbox(service).connection() for service in ("default", "registry")]
    ids = [connection.container for connection in connections]
    if not all(ids):
        raise RuntimeError("Could not identify owned sandbox containers")
    proc = await asyncio.create_subprocess_exec(
        "docker", "inspect", *ids,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    data, _ = await proc.communicate()
    if proc.returncode:
        raise RuntimeError("Could not inspect owned sandbox containers")
    containers = json.loads(data)
    networks = sorted({key for item in containers for key in item["NetworkSettings"]["Networks"]})
    proc = await asyncio.create_subprocess_exec(
        "docker", "network", "inspect", *networks,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    network_data, _ = await proc.communicate()
    if proc.returncode:
        raise RuntimeError("Could not inspect owned sandbox networks")
    details = json.loads(network_data)
    evidence = {
        "containers": [{
            "id": item["Id"], "image": item["Image"], "mounts": item["Mounts"],
            "ports": item["NetworkSettings"]["Ports"],
            "privileged": item["HostConfig"]["Privileged"],
            "network_mode": item["HostConfig"]["NetworkMode"],
        } for item in containers],
        "networks": [{"name": item["Name"], "internal": item["Internal"]} for item in details],
    }
    provider.save(root / "evidence" / scope / "containment.json", evidence)
    if not all(item["internal"] for item in evidence["networks"]):
        raise RuntimeError("Sandbox network is not internal")
    if any(item["mounts"] or any(item["ports"].values()) or item["privileged"]
           for item in evidence["containers"]):
        raise RuntimeError("Unexpected host access on sandbox")


def instrument(task, root, condition, ordinal):
    @solver
    def begin():
        async def solve(state, generate):
            scope = f"{condition}/{MODEL}/epoch-{ordinal:03d}"
            provider.SCOPE.set(scope)
            state.metadata["direct_scope"] = scope
            provider.event("sample_started", scope=scope, model=MODEL,
                           sample_id=state.sample_id, epoch=ordinal)
            await containment(root, scope)
            return state
        return solve

    @solver
    def seeded():
        async def solve(state, generate):
            await capture(root, state.metadata["direct_scope"], "initial")
            provider.save(
                root / "evidence" / state.metadata["direct_scope"] / "initial-messages.json",
                [message.model_dump(mode="json") for message in state.messages],
            )
            return state
        return solve

    original_setup = task.setup
    stages = original_setup if isinstance(original_setup, list) else (
        [original_setup] if original_setup else []
    )
    task.setup = chain(begin(), *stages, seeded())
    original_cleanup = task.cleanup

    async def cleanup(state):
        scope = state.metadata.get("direct_scope", f"{condition}/{MODEL}/unknown")
        provider.SCOPE.set(scope)
        await capture(root, scope, "final")
        provider.save(root / "evidence" / scope / "final-state.json", {
            "sample_id": state.sample_id,
            "epoch": ordinal,
            "messages": [message.model_dump(mode="json") for message in state.messages],
            "output": state.output.model_dump(mode="json") if state.output else None,
            "metadata": state.metadata,
        })
        provider.event("sample_cleanup", scope=scope, model=MODEL)
        if original_cleanup:
            await original_cleanup(state)

    task.cleanup = cleanup
    task.model = get_model(f"axonhub_step2/{MODEL}")
    task.epochs = 1
    task._name = f"lw_step2_{condition}_{MODEL.replace('.', '_').replace('-', '_')}_{ordinal:03d}"
    return task


async def execute(tasks, log_dir):
    return await eval_async(
        tasks,
        log_dir=str(log_dir),
        log_format="eval",
        epochs=1,
        max_tasks=2,
        max_samples=2,
        max_sandboxes=2,
        max_subprocesses=12,
        fail_on_error=False,
        retry_on_error=0,
        score_on_error=False,
        log_realtime=True,
        log_samples=True,
        log_model_api=True,
        log_refusals=True,
        sandbox_cleanup=True,
        reasoning_effort="high",
        reasoning_summary="auto",
        max_connections=1,
        max_retries=0,
        timeout=300,
    )


async def transport_preflight(root):
    provider.SCOPE.set(f"preflight/{MODEL}")
    model = get_model(f"axonhub_step2/{MODEL}")
    tools = [ToolInfo(
        name="check_sum",
        description="Add two integers.",
        parameters=ToolParams(
            properties={"a": ToolParam(type="integer"), "b": ToolParam(type="integer")},
            required=["a", "b"],
        ),
    )]
    messages = [
        ChatMessageSystem(content="Use the supplied tool for arithmetic."),
        ChatMessageUser(content="Use check_sum to add 17 and 25, then give the answer."),
    ]
    first = await model.generate(
        messages, tools=tools, config=GenerateConfig(reasoning_effort="high", max_retries=0)
    )
    calls = first.message.tool_calls or []
    if len(calls) != 1 or calls[0].function != "check_sum":
        raise RuntimeError("AxonHub tool-call preflight failed")
    call = calls[0]
    messages.extend([
        first.message,
        ChatMessageTool(content="42", tool_call_id=call.id, function=call.function),
    ])
    second = await model.generate(
        messages, tools=tools, config=GenerateConfig(reasoning_effort="high", max_retries=0)
    )
    if "42" not in second.completion:
        raise RuntimeError("AxonHub follow-up preflight failed")
    provider.save(root / "preflight" / "transport.json", {
        "passed": True,
        "actual_model": second.model,
        "tool_call": asdict(call),
        "final": second.completion,
        "reasoning_effort": "high",
        "counted_in_study": False,
    })


async def docker_preflight(root):
    from alignment_auditor.docker_replication.harness.scaffolds import react_solver
    env = root / "source/src/alignment_auditor/docker_replication/env/compose.yaml"
    task = Task(
        dataset=[Sample(
            id="transport-only",
            input="Run printf 'DOCKER_TOOL_OK\\n' with bash, then submit the observed output.",
        )],
        solver=react_solver(4, persona="Complete the user's task."),
        sandbox=("docker", str(env)),
        turn_limit=4,
        time_limit=180,
        config=GenerateConfig(temperature=1.0),
    )
    task = instrument(task, root, "preflight_docker", 0)
    logs = await execute([task], root / "preflight/docker")
    if len(logs) != 1 or logs[0].status != "success" or len(logs[0].samples or []) != 1:
        raise RuntimeError("Docker transport preflight failed")
    sample = logs[0].samples[0]
    if sample.error:
        raise RuntimeError("Docker transport preflight returned a sample error")
    if not any(message.role == "tool" and "DOCKER_TOOL_OK" in message.text
               for message in sample.messages):
        raise RuntimeError("Docker tool output was not observed")
    provider.save(root / "preflight" / "docker.json", {
        "passed": True, "model": MODEL, "counted_in_study": False,
    })


def refusal_candidate(sample):
    phrases = (
        "i can't assist with", "i cannot assist with", "i can't help with",
        "i cannot help with", "policy prevents", "not able to assist with that request",
    )
    texts = []
    for message in sample.messages:
        if message.role == "assistant":
            texts.append(message.text or "")
    if sample.output:
        texts.append(sample.output.completion or "")
    combined = "\n".join(texts).lower()
    return next((phrase for phrase in phrases if phrase in combined), None)


def progress(root, rows):
    per_cell = {}
    for condition in CELLS:
        selected = [row for row in rows if row["condition"] == condition]
        per_cell[condition] = {
            "attempted": len(selected),
            "scored": sum(row["scored"] for row in selected),
            "target": TARGET_PER_CELL,
            "errors": sum(row["error"] is not None for row in selected),
        }
    provider.save(root / "progress.json", {
        "updated_at": now(),
        "attempted": len(rows),
        "scored": sum(row["scored"] for row in rows),
        "scheduled": TARGET_PER_CELL * len(CELLS),
        "per_cell": per_cell,
    })


async def collect(root, parent):
    prepare(root, parent)
    transport = json.loads((root / "preflight/transport.json").read_text())
    docker = json.loads((root / "preflight/docker.json").read_text())
    if not transport["passed"] or transport["actual_model"] != MODEL or not docker["passed"]:
        raise RuntimeError("Preflight evidence does not match the frozen model and environment")
    provider.save(root / "started.json", {
        "time": now(), "pid": os.getpid(),
        "scheduled": TARGET_PER_CELL * len(CELLS),
    })
    provider.event("collection_started", scheduled=TARGET_PER_CELL * len(CELLS))
    rows = []
    progress(root, rows)
    try:
        for ordinal in range(1, TARGET_PER_CELL + 1):
            verify_source(root)
            tasks = [instrument(source_task(root, condition), root, condition, ordinal)
                     for condition in CELLS]
            provider.event("pair_started", ordinal=ordinal, conditions=list(CELLS))
            logs = await execute(tasks, root / "evals" / f"ordinal-{ordinal:03d}")
            if len(logs) != len(CELLS):
                raise RuntimeError(f"Ordinal {ordinal} returned {len(logs)} logs")
            for log in logs:
                samples = log.samples or []
                if len(samples) != 1:
                    raise RuntimeError(f"Expected one sample in {log.location}")
                sample = samples[0]
                scope = sample.metadata.get("direct_scope", "")
                condition = scope.split("/", 1)[0]
                refusal = refusal_candidate(sample)
                row = {
                    "condition": condition,
                    "ordinal": ordinal,
                    "scope": scope,
                    "log": log.location,
                    "status": log.status,
                    "scored": sample.error is None and bool(sample.scores),
                    "error": sample.error.model_dump(mode="json") if sample.error else None,
                    "refusal_candidate": refusal,
                    "scores": {name: value.model_dump(mode="json")
                               for name, value in (sample.scores or {}).items()},
                }
                rows.append(row)
                provider.save(root / "trial-index.json", rows)
                progress(root, rows)
                provider.event("trial_recorded", condition=condition, ordinal=ordinal,
                               scored=row["scored"], error=row["error"], refusal=refusal)
                if refusal:
                    provider.save(root / "refusal-alert.json", row)
                    raise RuntimeError(f"Refusal candidate in {scope}: {refusal}")
                if sample.error or log.status != "success" or not row["scored"]:
                    raise RuntimeError(f"Trial did not complete cleanly: {scope}")
        provider.save(root / "completion.json", {
            "time": now(), "status": "complete", "attempted": len(rows),
            "scored": sum(row["scored"] for row in rows),
        })
        provider.event("collection_completed", attempted=len(rows))
    except BaseException as error:
        provider.save(root / "collector-failure.json", {
            "time": now(), "type": type(error).__name__, "message": str(error),
            "recorded_trials": len(rows),
        })
        provider.event("collection_stopped", type=type(error).__name__, message=str(error))
        raise


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("prepare", "preflight", "collect"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pinned-parent", type=Path, required=True)
    parser.add_argument("--key-file", type=Path)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["SWH_LW_STEP2_OUTPUT"] = str(root)
    os.environ["INSPECT_DISPLAY"] = "plain"
    if args.key_file:
        os.environ["AXONHUB_API_KEY"] = args.key_file.expanduser().read_text().strip()
    prepare(root, args.pinned_parent)
    sys.path.insert(0, str(root / "source/src"))
    if args.phase == "prepare":
        print("Registered 64 protein_bank and 64 protein_none trials; no model call made.")
    elif args.phase == "preflight":
        await transport_preflight(root)
        await docker_preflight(root)
        print("AxonHub and Docker preflights passed; neither is counted in the study.")
    else:
        await collect(root, args.pinned_parent)


if __name__ == "__main__":
    asyncio.run(main())
