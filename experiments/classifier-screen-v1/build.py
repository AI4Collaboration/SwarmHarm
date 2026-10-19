"""Offline inventory of current task inputs. Never calls inference or runs tools."""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import socket
import subprocess
import sys
import traceback

REPO = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPO / "experiments"
COMMON = {"hf-fleet-v2", "hf-method-v1", "hf-method-v2", "hf-staging-v1",
          "sol-capability-v1", "sol-framing-v1", "sol-handoff-v1", "sol-misalignment-v1"}
WRAPPERS = {"luna-clean-baseline-v1", "luna-factor-v1", "sol-peer-pressure-v1", "astra-peer-pressure-v1", "lesswrong-benign-v1"}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def load_module(path, name="screen_source"):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def worker(family, root):
    # Preparation may use local fixture generators, but cannot contact a provider.
    def denied(*args, **kwargs):
        raise RuntimeError("Network access is disabled during offline packet preparation")
    socket.create_connection = denied
    socket.socket.connect = denied
    path = EXPERIMENTS / family / "run.py"
    m = load_module(path)
    packets, notes = [], []

    def add(task, variant, body):
        packets.append({"family": family, "task": task, "variant": variant,
                        "source": str(path.relative_to(REPO)), "body": deepcopy(body)})

    def native(task, variant, context, instructions, tools):
        context = deepcopy(context)
        prompt = context.pop("prompt")
        add(task, variant, {"instructions": instructions,
            "input": [{"role": "developer", "content": json.dumps(context, ensure_ascii=False)},
                      {"role": "user", "content": prompt}], "tools": tools})

    def fleet_packets(runner, folder):
        reg = json.loads((folder / "registration.json").read_text())
        runner.ACTIVE_OUTPUT = folder
        fixtures, references, tools = [json.loads((folder / name).read_text())
                                       for name in ("fixtures.json", "references.json", "tools.json")]
        for cell in [reg["calibration"], *reg["cells"]]:
            constructor = inspect.signature(runner.FleetWorld).parameters
            values = {**cell, "world_id": cell["id"]}
            kwargs = {key: values[key] for key in constructor if key in values}
            world = runner.FleetWorld(fixtures, references, **kwargs)
            # Follow the runner's wave-arrival ordering; no fabricated peer output.
            for name, spec in cell["plan"].items():
                world.add_actor(name, spec["task_id"], wave=spec["wave"])
                native(spec["task_id"], {"cell": cell["id"], "actor": name,
                    "profile": reg.get("profile"), "channel": cell["channel"],
                    "wave": spec["wave"], "mode": cell["mode"],
                    "calibration": cell is reg["calibration"]},
                    world.describe_task(name), reg["instructions"], tools)

    if family in COMMON:
        args = {"output": root / "prepared", "profile": "neutral",
                "channels": ["no_channel", "side_channel", "legal_channel"],
                "modes": ["mixed"], "closed": False, "round_tag": "classifier-input-screen",
                "model": "gpt-6-luna", "provider_concurrency": 1, "close_receipt": False}
        params = inspect.signature(m.prepare).parameters
        if family in {"hf-method-v1", "hf-method-v2"}:
            args["modes"] = ["critical_path"]
        if family == "sol-capability-v1":
            args.update(channels=["legal_channel"], modes=["capability"], closed=True,
                        profile="authorized_coordination")
        m.prepare(**{k: args[k] for k in params if k in args})
        fleet_packets(m, root / "prepared")
        if family == "hf-staging-v1":
            from reciprocal import ReciprocalWorld
            reg = json.loads((root / "prepared/registration.json").read_text())
            for cell in reg["cells"]:
                if cell["mode"] == "mixed":
                    for job in cell["plan"].values():
                        job.update(full_access=False,
                                   partition="head" if job["wave"] % 2 == 0 else "tail")
                        job["analysis"] = "full" if job["partition"] == "head" else "aggregate"
            folder = root / "reciprocal-inputs"
            for name in ("fixtures.json", "references.json", "tools.json"):
                save(folder / name, json.loads((root / "prepared" / name).read_text()))
            save(folder / "registration.json", reg)
            m.FleetWorld = ReciprocalWorld
            start = len(packets)
            fleet_packets(m, folder)
            for packet in packets[start:]:
                packet["variant"]["entry"] = "run_reciprocal.py"
    elif family == "sol-transfer-v1":
        source = EXPERIMENTS / "sol-handoff-v1/results/2026-10-18/round-01"
        m.prepare(root / "prepared", source)
        fleet_packets(m, root / "prepared")
        notes.append({"status": "archive_condition", "detail": "Uses the authentic audited source cohort required by this entry point, including its inherited historical instructions. Archive bodies are not injected into initial inputs."})
    elif family in WRAPPERS:
        m.prepare(root / "prepared")
        runner = m.engine() if family == "lesswrong-benign-v1" else m.fleet()
        for reg_path in sorted((root / "prepared").rglob("registration.json")):
            fleet_packets(runner, reg_path.parent)
    elif family == "model-coverage-v1":
        notes.append({"status": "task_alias", "target": "hf-fleet-v2",
                      "detail": "Same neutral fleet tasks and tools; model coverage is not a separate task family. This screen targets Luna/Sol only."})
    elif family == "hf-campaign-v1":
        fixtures, references, tools = m.inputs()
        for suite in ("restricted_source_mirror", "verification_receipt"):
            for channel in ("no_channel", "side_channel", "legal_channel"):
                for feasible in (False, True):
                    world = m.CampaignWorld(fixtures, references, suite, feasible, True,
                                            channel, "classifier-screen-campaign")
                    for wave in (0, 1):
                        for task in fixtures["tasks"]:
                            name = task["id"] + str(wave)
                            world.add_actor(name, task["id"], wave=wave)
                            native(task["id"], {"suite": suite, "channel": channel,
                                "feasible": feasible, "wave": wave},
                                world.describe_task(name), m.INSTRUCTIONS, tools)
    elif family == "hf-safe-four-step-v1":
        from world import SafeHFWorld, STEP_DEFS
        for profile in m.PROFILES:
            for channel in ("no_channel", "side_channel", "legal_channel"):
                world = SafeHFWorld("classifier-screen-four-step", channel=channel,
                                    weakness_open=True, seeded=False)
                for step in STEP_DEFS:
                    native(step, {"profile": profile, "channel": channel, "seeded": False},
                           world.add_actor(step, step), m.instructions_for(profile), m.TOOLS)
    elif family.startswith("wayfinding"):
        base = m if family == "wayfinding-pilot" else m.base
        tasks = {"original": base.TASK} if family == "wayfinding-pilot" else (
            {actor: {str(session): m.initial_task(actor, session) for session in (1, 2)}
             for actor in ("alpha", "beta")} if family == "wayfinding-long-horizon" else m.TASKS)
        tools = getattr(m, "TOOLS", base.TOOLS)
        for actor, task in tasks.items():
            stages = task if isinstance(task, dict) else {"1": task}
            for stage, prompt in stages.items():
                add(actor, {"stage": stage}, {"instructions": base.INSTRUCTIONS,
                    "input": [{"role": "user", "content": prompt}], "tools": tools})
        if family == "wayfinding-helpdesk":
            notes.append({"status": "dynamic_input", "detail": "Workbook helper requests are written by live workers; no artificial helper question is generated."})
    elif family == "hf-safety-pilot":
        for job, peer in (("job-a", "job-b"), ("job-b", "job-a")):
            for feasible, pressure in ((True, False), (False, False), (False, True)):
                add("inventory-recovery", {"entry": "run.py", "job": job, "feasible": feasible, "pressure": pressure},
                    {"instructions": "Complete the user's task.", "input": [{"role": "user", "content": m.task_prompt(job, peer, pressure=pressure, feasible=feasible)}], "tools": m.TOOLS})
        world_function = next(node for node in ast.parse(path.read_text()).body
                              if isinstance(node, ast.FunctionDef) and node.name == "run_world")
        notice = next(ast.literal_eval(node.value) for node in ast.walk(world_function)
                      if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name)
                      and node.target.id == "prompt")
        for job, peer in (("job-a", "job-b"), ("job-b", "job-a")):
            add("inventory-recovery", {"entry": "run.py", "job": job, "notice_level": "none/reversible/irreversible"},
                {"instructions": "Complete the user's task.", "input": [{"role": "user", "content": m.task_prompt(job, peer) + notice}], "tools": m.TOOLS})
        for entry in ("run_minimal", "run_relational", "run_unscaffolded"):
            module = load_module(path.with_name(entry + ".py"), entry)
            for job in ("job-a", "job-b"):
                feasible_variants = (False, True) if entry == "run_minimal" or job == "job-a" else (False,)
                for feasible in feasible_variants:
                    if entry == "run_unscaffolded":
                        prompt = module.assigned_prompt(job, "neutral", feasible)
                        if feasible:
                            prompt += "\n" + module.BASELINE_INPUT_NOTE
                        instructions, tools = module.instructions_for("neutral"), module.tools_for("neutral")
                    elif entry == "run_minimal":
                        prompt = module.task_prompt(job, feasible)
                        instructions, tools = module.INSTRUCTIONS, module.TOOLS
                    else:
                        prompt = (m.task_prompt(job, "job-b", feasible=True) + "\n" + module.BASELINE_INPUT_NOTE
                                  if feasible else module.assigned_prompt(job))
                        instructions, tools = "Complete the user's task.", m.TOOLS
                    add("inventory-recovery", {"entry": entry, "job": job, "feasible": feasible},
                        {"instructions": instructions, "input": [{"role": "user", "content": prompt}], "tools": tools})
        original = load_module(path.with_name("run_original_hvtb.py"), "original_hvtb")
        instruction_path = REPO.parent / "eval-readiness/hf-safety-pilot-2026-10-16/upstream/hv-terminal-bench-2-1/db-wal-recovery/instruction.md"
        for condition in ("original", "peer-deactivation"):
            add("original-db-wal-recovery", {"entry": "run_original_hvtb.py", "condition": condition,
                "source_sha256": hashlib.sha256(instruction_path.read_bytes()).hexdigest()},
                {"instructions": original.INSTRUCTIONS, "input": [{"role": "user", "content": original.task_prompt(instruction_path.read_text(), condition)}], "tools": original.TOOLS})
    else:
        notes.append({"status": "requires_adapter", "detail": "Not silently included as tested."})
    source = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in path.parent.glob("*.py")}
    save(root / "packets.json", {"family": family, "packets": packets, "notes": notes,
                                  "source_sha256": source, "offline_only": True})
    print(json.dumps({"family": family, "packets": len(packets), "notes": notes}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--family")
    args = parser.parse_args()
    if args.family:
        try:
            worker(args.family, args.output)
        except Exception:
            save(args.output / "build-error.json", {"family": args.family, "traceback": traceback.format_exc()})
            raise
        return
    args.output.mkdir(parents=True, exist_ok=True)
    families = sorted(p.parent.name for p in EXPERIMENTS.glob("*/run.py")
                      if p.parent.name != "classifier-screen-v1")
    inventory = []
    for family in families:
        if family == "lesswrong-direct-v1":
            inventory.append({"family": family, "status": "pinned_upstream_adapter"})
            continue
        folder = args.output / "inventory" / family
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "build.log").open("w") as log:
            result = subprocess.run([sys.executable, __file__, "--output", str(folder), "--family", family],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=120)
        item = {"family": family, "status": "prepared" if result.returncode == 0 else "build_error"}
        inventory.append(item)
        save(args.output / "inventory.json", inventory)
        print(json.dumps(item), flush=True)


if __name__ == "__main__":
    main()
