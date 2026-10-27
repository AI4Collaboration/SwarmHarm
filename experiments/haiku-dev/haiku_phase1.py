"""Exploratory Phase 1 rollout of the current SwarmHarm environment on Claude via the Anthropic API.

Unregistered development run. It imports the maintained SwarmHarm modules
read-only (World, tools, platform feedback text, live Phase 1 gate) and replaces
only the model transport and the scheduler loop. It cannot support a campaign
claim: no frozen registration, direct Anthropic routing instead of AxonHub, a
different workstation image ID and Phase 1 only.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import anthropic

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "experiments/swarmharm-v1"
sys.path.insert(0, str(HERE))
import run as runner  # noqa: E402  (frozen helpers; requires Harbor 0.24.0)
import lab  # noqa: E402
import review  # noqa: E402

REGISTRATION = HERE / "registrations/2026-10-27-current-work-glm-r16/registration.json"


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")
    tmp.replace(path)


def api_key(key_file):
    if key_file:
        return Path(key_file).expanduser().read_text().strip()
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return os.environ["ANTHROPIC_API_KEY"].strip()
    env = REPO / ".env"  # git-ignored
    if env.exists():
        for line in env.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ANTHROPIC_API_KEY":
                return value.strip().strip("'\"")
    return ""


def anthropic_tools(definitions):
    # World.call validates arguments against the same JSON schema.
    return [{
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["parameters"],
    } for tool in definitions]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--effort", default="high")
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--image", default="python:3.12-slim")
    parser.add_argument("--key-file")
    parser.add_argument("--max-actor-seconds", type=int, default=3600)
    parser.add_argument("--max-campaign-seconds", type=int, default=4500)
    parser.add_argument("--max-requests", type=int, default=400,
                        help="cost guard across all agents")
    parser.add_argument("--run-past-gate", action="store_true",
                        help="keep Phase 1 running after the gate instead of stopping")
    args = parser.parse_args()

    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; use a fresh output directory")
    root = out / "natural"
    key = api_key(args.key_file)
    if not key:
        raise SystemExit("Set ANTHROPIC_API_KEY, add it to the repo .env or pass --key-file")
    client = anthropic.Anthropic(api_key=key, max_retries=2, timeout=300)

    image_id = subprocess.run(
        ["docker", "image", "inspect", args.image, "--format", "{{.Id}}"],
        capture_output=True, text=True, check=True).stdout.strip()
    lab.base.IMAGE = image_id

    reg = json.loads(REGISTRATION.read_text())
    deadline = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(
        minute=0, second=0, microsecond=0)
    plan = deepcopy(reg["plan"]["natural"])
    for item in plan.values():
        item["provider"] = "anthropic"
        item["business_pressure"]["release_deadline_utc"] = deadline.isoformat()
    reg["plan"]["natural"] = plan
    cue = reg["cue_condition"]
    followup_seconds = reg["completion_protocol"].get("unfinished_work_followup_seconds")
    publication = reg.get("source_publication")

    world = lab.World(plan, root / "operator", reg.get("topology"))
    actors = sorted(plan)
    system, histories, tools, states = {}, {}, {}, {}
    for actor in actors:
        initial = lab.initial(plan, actor)
        developer, user = initial["input"]
        system[actor] = [{"type": "text", "text": initial["instructions"]},
                         {"type": "text", "text": developer["content"]}]
        histories[actor] = [{"role": "user", "content": user["content"]}]
        tools[actor] = anthropic_tools(lab.tools(plan[actor]))
        states[actor] = {"actor": actor, "status": "running", "steps": 0, "tools": 0,
                         "completion_attempts": [], "platform_notifications": []}
        save(root / actor / "initial-input.json", {
            "system": system[actor], "messages": histories[actor], "tools": tools[actor]})

    save(out / "run-meta.json", {
        "kind": "exploratory_unregistered_phase1_only",
        "model": args.model, "effort": args.effort, "max_tokens": args.max_tokens,
        "thinking": {"type": "adaptive"}, "parallel_tool_use": False,
        "prompt_caching": {"type": "ephemeral", "placement": "automatic"},
        "transport": "Anthropic Messages API via anthropic SDK (streaming)",
        "image": args.image, "image_id": image_id, "registered_image": reg["image"],
        "environment_source": str(REGISTRATION.relative_to(REPO)),
        "repo_head": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                    capture_output=True, text=True).stdout.strip(),
        "cue_condition": cue, "scenario": reg["scenario"],
        "phase1_gate_revision": reg["phase1_gate_revision"],
        "release_deadline_utc": deadline.isoformat(),
        "limits": {"max_actor_seconds": args.max_actor_seconds,
                   "max_campaign_seconds": args.max_campaign_seconds,
                   "max_requests": args.max_requests},
        "differences_from_registered_campaign": [
            "direct Anthropic API instead of AxonHub Responses transport",
            "developer metadata sent as a second system text block",
            "workstation image is a fresh python:3.12-slim pull, not the pinned image ID",
            "release deadline set to two hours after launch",
            "Phase 1 only; stops after the live gate unless --run-past-gate",
            "no registration, seal or evidence manifest",
        ],
    })

    def signal(actor):
        return world.activity_signal(actor)

    delivered = {actor: signal(actor) for actor in actors}
    requests = {"started": 0}
    gate = {"passed": None}
    began = time.monotonic()
    starts = {}

    def infer(actor, step):
        folder = root / actor / "trace"
        body = {
            "model": args.model, "max_tokens": args.max_tokens,
            "system": system[actor], "messages": histories[actor], "tools": tools[actor],
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": args.effort},
            # Automatic caching of the growing, append-only history prefix.
            "cache_control": {"type": "ephemeral"},
        }
        save(folder / f"{step:04d}.request.json", body)
        started = utc()
        with client.messages.stream(**body) as stream:
            message = stream.get_final_message()
        value = message.to_dict()
        value["_timing"] = {"started_at": started, "finished_at": utc()}
        save(folder / f"{step:04d}.response.json", value)
        return value

    def append_user_text(actor, text):
        last = histories[actor][-1]
        if last["role"] == "user":
            if isinstance(last["content"], str):
                last["content"] = [{"type": "text", "text": last["content"]}]
            last["content"].append({"type": "text", "text": text})
        else:
            histories[actor].append({"role": "user", "content": text})

    def export(actor=None):
        save(root / "world.json", world.snapshot())
        save(root / "summary.json", world.summary())
        for name in ([actor] if actor else actors):
            save(root / name / "history.json", histories[name])
            save(root / name / "result.json", states[name])

    futures = {}

    def submit(pool, actor, unfinished=False):
        state = states[actor]
        state.pop("unfinished_followup_at", None)
        if requests["started"] >= args.max_requests:
            state["status"] = "request_cap"
            return
        step = state["steps"] + 1
        sig = signal(actor)
        message, kind = None, None
        if unfinished and not runner.campaign_completion_state(world, actor)["complete"]:
            message, kind = runner.unfinished_work_feedback(), "unfinished_work_followup"
        elif sig["revision"] != delivered[actor]["revision"]:
            if sig["source_publication_event"] != delivered[actor]["source_publication_event"]:
                message = runner.build_publication_feedback()
            else:
                message = runner.platform_update_feedback(cue, reg["scenario"])
            kind = "relevant_platform_change"
            delivered[actor] = sig
        if message is not None:
            append_user_text(actor, message)
            notice = {"step": step, "at": utc(), "kind": kind, "text": message,
                      "relevant_cross_job_records": sig["relevant_cross_job_records"]}
            state["platform_notifications"].append(notice)
            save(root / actor / "trace" / f"{step:04d}-platform-update.json", notice)
        state["status"] = "running"
        requests["started"] += 1
        futures[pool.submit(infer, actor, step)] = (actor, step)

    def progress(phase):
        save(out / "progress.json", {
            "updated_at": utc(), "phase": phase,
            "elapsed_seconds": round(time.monotonic() - began, 1),
            "requests_started": requests["started"], "events": len(world.events),
            "gate_passed": gate["passed"] is not None,
            "states": {a: {k: states[a][k] for k in ("status", "steps", "tools")} for a in actors},
            "filed": sum(row["submitted_reviews"] for row in world.summary()),
        })

    termination = "quiescence"
    try:
        world.prepare_workstations(actors, max_workers=len(actors))
        activated_at = utc()
        save(root / "activation.json", {"policy": "simultaneous_start_barrier",
                                        "activated_at": activated_at, "actors": actors})
        export()
        with ThreadPoolExecutor(max_workers=len(actors)) as pool:
            for actor in actors:
                starts[actor] = time.monotonic()
                submit(pool, actor)
            while True:
                now = time.monotonic()
                if now - began >= args.max_campaign_seconds or any(
                        now - starts[a] >= args.max_actor_seconds for a in actors):
                    termination = "time_limit"
                    break
                if gate["passed"] is not None and not args.run_past_gate:
                    if not futures:
                        termination = "phase1_gate_passed"
                        break
                else:
                    for actor in actors:
                        due = states[actor].get("unfinished_followup_at")
                        if states[actor]["status"] == "waiting" and due is not None and due <= now:
                            submit(pool, actor, unfinished=True)
                    if (publication and world.source_publication_event is None
                            and now - began >= publication["after_start_seconds"]):
                        world.publish_final_build()
                        export()
                        for actor in actors:
                            if states[actor]["status"] == "waiting":
                                submit(pool, actor)
                if not futures:
                    pending = (any(s.get("unfinished_followup_at") for s in states.values())
                               or (publication and world.source_publication_event is None))
                    if pending and gate["passed"] is None:
                        time.sleep(1)
                        continue
                    if requests["started"] >= args.max_requests:
                        termination = "request_cap"
                    break
                done, _ = wait(tuple(futures), timeout=1, return_when=FIRST_COMPLETED)
                if not done:
                    continue
                future = next(iter(done))
                actor, step = futures.pop(future)
                state = states[actor]
                value = future.result()
                state["steps"] = step
                histories[actor].append({"role": "assistant", "content": value["content"]})
                if value.get("stop_reason") == "refusal":
                    state["status"] = "refusal"
                    save(root / actor / "refusal.json", value)
                    termination = "refusal"
                    export(actor)
                    break
                calls = [b for b in value["content"] if b["type"] == "tool_use"]
                if not calls:
                    text = "".join(b.get("text", "") for b in value["content"] if b["type"] == "text")
                    check = runner.campaign_completion_state(world, actor)
                    state["completion_attempts"].append(
                        {"step": step, "at": utc(), "text": text, "completion_state": check})
                    if followup_seconds and not check["complete"]:
                        state["unfinished_followup_at"] = time.monotonic() + followup_seconds
                    if signal(actor)["revision"] != delivered[actor]["revision"] and gate["passed"] is None:
                        submit(pool, actor)
                    else:
                        state["status"] = "waiting"
                    export(actor)
                    progress("running")
                    continue
                results = []
                for index, call in enumerate(calls, 1):
                    state["tools"] += 1
                    result = world.call(actor, step, call["name"], call["input"])
                    event = world.events[-1]
                    save(root / actor / "trace" / f"{step:04d}-tool-{index}.json",
                         {"event_id": event["id"], "name": call["name"],
                          "arguments": call["input"], "result": result})
                    results.append({"type": "tool_result", "tool_use_id": call["id"],
                                    "content": json.dumps(result, ensure_ascii=False)})
                histories[actor].append({"role": "user", "content": results})
                if world.observation_error is not None:
                    raise RuntimeError(str(world.observation_error))
                if gate["passed"] is None:
                    candidate = review.runtime_formation_evidence(reg, world.snapshot())
                    if candidate["passed"]:
                        gate["passed"] = {"at": utc(), "elapsed_seconds": round(time.monotonic() - began, 2),
                                          "requests_started": requests["started"], **candidate}
                        save(root / "phase1-gate.json", gate["passed"])
                export(actor)
                progress("running")
                if gate["passed"] is None or args.run_past_gate:
                    submit(pool, actor)
                else:
                    state["status"] = "stopped_after_gate"
    finally:
        cleanup = world.close()
        export()
        save(out / "completion.json", {"finished_at": utc(), "termination": termination,
                                       "elapsed_seconds": round(time.monotonic() - began, 2),
                                       "requests_started": requests["started"],
                                       "gate_passed": gate["passed"] is not None,
                                       "containers_removed": cleanup})
        progress(termination)
    print(json.dumps({"termination": termination, "gate_passed": gate["passed"] is not None,
                      "requests": requests["started"], "out": str(out)}))


if __name__ == "__main__":
    main()
