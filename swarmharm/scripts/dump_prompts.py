#!/usr/bin/env python3
"""Write each reporting agent's declared inputs and workstation files to Markdown."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from inspect_unified_input import REPO, build_preview
import domain_runtime
from jsonschema import ValidationError
from claude_agent import SYSTEM_PROMPT as CLAUDE_PROMPT
from codex_gateway import SYSTEM_PROMPT as CODEX_PROMPT
from phase1 import lab
from phase2 import phase2_component, unified_delivery
from guardrails import controller_harness, outside_repository, require_unified_workflow


def fence(text, language=""):
    ticks = chr(96) * 3
    while ticks in text:
        ticks += chr(96)
    return ticks + language + "\n" + text + ("" if text.endswith("\n") else "\n") + ticks


def json_block(value):
    return fence(json.dumps(value, indent=2, ensure_ascii=False), "json")


def registered_inputs(folder):
    metadata = (folder / "registration.json").read_bytes()
    digest = hashlib.sha256(metadata).hexdigest()
    if json.loads((folder / "registration-seal.json").read_bytes())["sha256"] != digest:
        raise ValueError("Registration seal differs")
    reg = json.loads(metadata)
    require_unified_workflow(reg["study_mode"], reg["phase2"]["component_family"])

    def sealed(name):
        data = (folder / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != reg["input_hashes"][name]:
            raise ValueError("Sealed input differs: " + name)
        return json.loads(data)["natural"]

    header = {"registration": folder.name, "registration_sha256": digest,
              "domain": domain_runtime.domain_for(domain_runtime.registered_workload(reg)),
              "workload": domain_runtime.registered_workload(reg),
              "recorded_scenario": reg["scenario"], "preset": reg["phase2"]["binding_preset"],
              "model": reg["models"], "harness": reg["harness"]["kind"],
              "goal_mode": reg["harness"]["goal_mode"],
              "system_prompt_config": reg["harness"].get("system_prompt"),
              "input_projection": reg["harness"].get("input_projection"),
              "continuation": reg["completion_protocol"]}
    return header, sealed("initial-input-audit.json"), sealed("initial-file-audit.json")


def configured_inputs(domain, preset, world, harness, workload=None, population=unified_delivery.cohort.DEFAULT_POPULATION):
    selected = domain_runtime.resolve_workload(domain, workload)
    manifest, subjects = build_preview(domain, preset, world, harness=harness, workload=workload, actors=unified_delivery.cohort.actor_ids(population))
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO))
    audits = {
        actor: {"instructions": lab.INSTRUCTIONS, "input": [{"role": "user", "content": task}],
                "tools": phase2_component.base_tools({"scenario": selected}, unified_delivery.FAMILY) + subjects["tools"]}
        for actor, task in subjects["tasks"].items()
    }
    header = {"preview_commit": commit, "working_tree_modified": dirty,
              "domain": manifest['domain'], "workload": selected,
              "preset": preset, "harness": harness, "goal_mode": "off", "world": manifest["world_config"],
              "system_prompt_config": CLAUDE_PROMPT if harness == "claude-code" else CODEX_PROMPT,
              "input_projection": controller_harness({"kind": harness})["input_projection"],
              "input_hashes": manifest["input_contract"]["subject_sha256"],
              "notification_detail": manifest["world_config"]["observation"].get("notification_detail", "generic")}
    return header, audits, subjects["initial_files"]


def render(actor, audit, files):
    lines = [f"# {actor}", "## Registered instructions", fence(audit["instructions"]),
             "## Initial messages"]
    for message in audit["input"]:
        lines.extend([message["role"], fence(message["content"])])
    lines.extend(["## Tools", json_block(audit["tools"]), "## Workstation files"])
    for name, encoded in sorted(files.items()):
        data = base64.b64decode(encoded, validate=True)
        try:
            body = fence(data.decode("utf-8"), {".py": "python", ".json": "json",
                         ".md": "markdown", ".csv": "csv"}.get(Path(name).suffix, ""))
        except UnicodeDecodeError:
            body = f"Binary file, {len(data)} bytes. SHA-256 {hashlib.sha256(data).hexdigest()}"
        lines.extend([f"### {name}", body])
    return "\n\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="New directory outside the checkout")
    parser.add_argument("--population", "--agents", "-N", type=int, help="Preview workstation count (default 3)")
    parser.add_argument("--registration-dir", type=Path, help="Read verified, sealed inputs for a collected case")
    parser.add_argument("--scenario", choices=domain_runtime.SUPPORTED)
    parser.add_argument("--workload", choices=domain_runtime.WORKLOADS)
    parser.add_argument("--binding-preset", choices=unified_delivery.PRESETS)
    parser.add_argument("--world-config", type=Path)
    parser.add_argument("--harness", choices=("codex", "claude-code"))
    args = parser.parse_args(argv)
    if args.registration_dir and any(value is not None for value in (
            args.scenario, args.workload, args.binding_preset, args.world_config, args.harness, args.population)):
        parser.error("Choose a sealed registration or a current configuration")
    default_dir = REPO.parent/"eval-readiness"/"prompt-dumps"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        output = outside_repository(args.output or default_dir, REPO, "Prompt dump")
        if args.registration_dir:
            folder = args.registration_dir.resolve()
            if output.is_relative_to(folder):
                raise ValueError("Choose an output directory outside the sealed registration")
            header, audits, files = registered_inputs(folder)
        else:
            domain, preset = args.scenario or "knowledge-work", args.binding_preset or "records"
            config_path = args.world_config or REPO/"swarmharm/configs/unified-balanced-envelope.json"
            header, audits, files = configured_inputs(domain, preset, json.loads(config_path.read_bytes()), args.harness or "codex", args.workload,
                args.population if args.population is not None else unified_delivery.cohort.DEFAULT_POPULATION)
        if not audits or set(files) != set(audits) or any(Path(a).name != a or not a.startswith("job-") for a in audits):
            raise ValueError("Expected matching, named reporting workstations")
        pages = {f"{a}.md": render(a, audits[a], files[a]) for a in audits}
        header["population"] = len(audits)
        index = ["# Reporting inputs", json_block(header),
                 "Each workstation page contains the declared task, tool schemas and initial files. "
                 "The native trajectory records the messages actually exchanged during a rollout."]
        index.extend(f"- [{a}]({a}.md)" for a in audits)
        pages["README.md"] = "\n\n".join(index) + "\n"
        output.mkdir(parents=True, exist_ok=False)
        for name, page in pages.items():
            (output/name).write_text(page, encoding="utf-8")
    except (OSError, ValueError, KeyError, ValidationError) as error:
        parser.error(str(error))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
