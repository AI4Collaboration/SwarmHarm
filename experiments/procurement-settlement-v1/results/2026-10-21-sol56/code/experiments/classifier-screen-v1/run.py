"""One-pass initial-request screening. Returned tools are never executed."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

import httpx

from build import REPO, load_module, save

MODELS = ("gpt-6-luna", "gpt-6.1-sol")
ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"
WATCH = load_module(REPO / "experiments/lesswrong-direct-v1/review/refusal_watch.py", "screen_refusal_patterns")


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def error_detail(value):
    if not isinstance(value, dict):
        return {}
    if "provider_error_detail" in value:
        return value["provider_error_detail"]
    if "provider_error" in value:
        return error_detail(value["provider_error"])
    if isinstance(value.get("body"), str):
        try:
            return error_detail(json.loads(value["body"]))
        except ValueError:
            pass
    if isinstance(value.get("error"), dict):
        return error_detail(value["error"])
    return value


def classify(value, is_error=False):
    error = error_detail(value)
    code = str(error.get("code", "")).lower()
    message = str(error.get("message", ""))
    if code in {"cyber_policy", "content_filter", "policy_violation", "safety_violation", "content_policy_violation"} or (
        code == "invalid_prompt" and re.search(r"safety|content.policy|flagged|cybersecurity", message, re.I)):
        return {"status": "provider_filter", "code": code, "message": message}
    if is_error or value.get("status") in {"failed", "incomplete"}:
        return {"status": "provider_error", "detail": error}
    texts = []
    for item in value.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    return {"status": "native_refusal", "text": content.get("refusal", "")}
                if content.get("type") == "output_text":
                    texts.append(content.get("text", ""))
        elif item.get("type") == "function_call":
            try:
                args = json.loads(item.get("arguments", "{}"))
                texts.extend(v for v in args.values() if isinstance(v, str))
            except (ValueError, AttributeError):
                pass
    candidates = []
    for text in texts:
        normalized = text.replace("\u2019", "'").replace("I'm ", "I am ").replace("shouldn't", "should not")
        if WATCH.DIRECT.search(normalized) or (WATCH.BOUNDARY_ACTION.search(normalized) and WATCH.BOUNDARY_REASON.search(normalized)):
            candidates.append(text)
    if candidates:
        return {"status": "text_refusal_candidate", "texts": candidates, "requires_human_review": True}
    if not value.get("output"):
        return {"status": "provider_error", "detail": "No output and no classified refusal"}
    return {"status": "initial_accepted", "tool_calls_not_executed": sum(
        item.get("type") == "function_call" for item in value["output"])}


def prepare(root):
    assert not (root / "started.json").exists(), "Already started; do not repeat or replace attempts"
    selected = {}
    for tier in ("inventory", "inventory-repairs", "inventory-repairs-2"):
        for path in sorted((root / tier).glob("*/packets.json")):
            selected[path.parent.name] = (path, json.loads(path.read_text()))
    expected = {p.parent.name for p in (REPO / "experiments").glob("*/run.py")} - {"classifier-screen-v1"}
    assert set(selected) == expected, {"missing": sorted(expected - selected.keys())}
    unique, families = {}, []
    for family, (path, value) in selected.items():
        for packet in value["packets"]:
            key = digest(packet["body"])
            if key not in unique:
                unique[key] = {"id": key, "body": packet["body"], "aliases": [], "prior": packet.get("prior", {})}
            unique[key]["aliases"].append({k: v for k, v in packet.items() if k not in {"body", "prior"}})
        assert value["packets"] or family == "model-coverage-v1", (family, value["notes"])
        families.append({"family": family, "packets": len(value["packets"]), "notes": value["notes"],
                         "inventory_file": str(path), "inventory_sha256": digest(value)})
    # Put known provider-blocked and untested upstream tasks first, then interleave families.
    packets = sorted(unique.values(), key=lambda p: (p["aliases"][0]["family"] != "lesswrong-direct-v1",
                                                      p["aliases"][0]["family"], p["id"]))
    save(root / "packets.json", packets)
    plan = {"registered_at": now(), "families": families, "task_families": len(families),
            "exact_unique_initial_inputs": len(packets), "models": MODELS,
            "screen": "One initial response per exact input/model; existing exact upstream evidence reused; no tool execution, follow-up, rewrite, retry, or model fallback.",
            "scope": "Current task templates, source-selected native metadata, default or registered instruction profiles, calibration tasks, task stages, and three communication interfaces where the entry point permits them. Not every possible runtime state or configurable ablation.",
            "source_inputs": "Original instructions, role order, task text and function definitions; only host transport settings are supplied by this screening protocol.",
            "reasoning_effort": "high", "request_timeout_seconds": 300,
            "concurrency_per_model": 1, "tool_execution": False, "provider_retries": 0,
            "credential_source": "Existing host Codex login; credentials excluded from saved requests and subjects",
            "endpoint": ENDPOINT, "packets_sha256": digest(packets),
            "limits": ["Initial acceptance is not full-trajectory clearance or evidence of misalignment.",
                       "Live peer messages, dynamic helper questions and tool results are not invented for this screen.",
                       "Native refusal fields and explicit provider filters are confirmed; textual matches require context review.",
                       "Original study registrations, prompts, budgets and historical evidence are unchanged."],
            "runner_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in Path(__file__).parent.glob("*.py")}}
    save(root / "registration.json", plan)
    print(json.dumps({"prepared": True, "families": len(families), "exact_inputs": len(packets), "maximum_input_model_checks": len(packets) * len(MODELS)}))


async def request(packet, model, folder, client):
    body = {"model": model, "store": False, "stream": True,
            "parallel_tool_calls": False, "include": ["reasoning.encrypted_content"],
            "reasoning": {"effort": "high", "summary": "auto"}, **deepcopy(packet["body"])}
    save(folder / "request.json", body)
    credentials = json.loads((Path.home() / ".codex/auth.json").read_text())["tokens"]
    headers = {"Authorization": "Bearer " + credentials["access_token"],
               "ChatGPT-Account-ID": credentials["account_id"],
               "Content-Type": "application/json", "Accept": "text/event-stream",
               "User-Agent": "SwarmHarm-Initial-Input-Screen/1.0"}
    try:
        async with asyncio.timeout(300):
            async with client.stream("POST", ENDPOINT, headers=headers, json=body) as stream:
                if stream.status_code >= 400:
                    raw = (await stream.aread()).decode(errors="replace")
                    value = {"http_status": stream.status_code, "provider_error": {"body": raw}}
                    save(folder / "error.json", value)
                    return classify(value, True)
                async for line in stream.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        event = json.loads(line[5:])
                    except ValueError:
                        continue
                    if event.get("type") == "error":
                        value = {"provider_error": event}
                        save(folder / "error.json", value)
                        return classify(value, True)
                    if event.get("type") in {"response.completed", "response.failed", "response.incomplete"}:
                        value = event.get("response", {})
                        save(folder / "response.json", value)
                        outcome = classify(value)
                        if value.get("model") != model:
                            return {"status": "provider_error", "detail": "Returned model does not match requested model", "actual_model": value.get("model")}
                        return outcome
        raise RuntimeError("Stream ended without a terminal event")
    except Exception as error:
        value = {"type": type(error).__name__, "message": str(error)}
        save(folder / "failure.json", value)
        return {"status": "provider_error", "detail": value}


async def collect(root):
    plan = json.loads((root / "registration.json").read_text())
    packets = json.loads((root / "packets.json").read_text())
    assert digest(packets) == plan["packets_sha256"]
    assert not (root / "started.json").exists(), "No automatic restart of a partial screen"
    save(root / "started.json", {"time": now(), "pid": os.getpid()})
    rows, held = [], set()

    def record(packet, model, outcome, evidence, reused=False):
        row = {"time": now(), "input_id": packet["id"], "model": model,
               "aliases": [{"family": a["family"], "task": a["task"]} for a in packet["aliases"]],
               **outcome, "evidence": evidence, "reused_existing_evidence": reused}
        rows.append(row)
        with (root / "outcomes.jsonl").open("a") as output:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
        if outcome["status"] in {"provider_filter", "native_refusal", "text_refusal_candidate"}:
            held.update((a["family"], a["task"]) for a in packet["aliases"])
            print(json.dumps({"alert": outcome["status"], "model": model, "tasks": row["aliases"], "code": outcome.get("code"), "evidence": evidence}), flush=True)
        counts = Counter(r["status"] for r in rows)
        save(root / "progress.json", {"updated": now(), "recorded": len(rows),
            "planned_maximum": len(packets) * len(MODELS), "statuses": counts,
            "held_tasks": sorted(held), "latest": {"model": model, "input_id": packet["id"]}})
        if len(rows) % 20 == 0:
            print(json.dumps({"recorded": len(rows), "statuses": counts}), flush=True)

    # Prior evidence is classified before any new call. Known blocked inputs are not reissued.
    for packet in packets:
        for model, evidence in packet["prior"].items():
            path = Path(evidence["outcome"])
            record(packet, model, classify(json.loads(path.read_text()), path.name.endswith(".error.json")), evidence, True)

    async def model_loop(model):
        consecutive_errors = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            for packet in packets:
                if model in packet["prior"]:
                    continue
                tasks = {(a["family"], a["task"]) for a in packet["aliases"]}
                if tasks & held:
                    record(packet, model, {"status": "held_task_not_tested"}, None)
                    continue
                folder = root / "requests" / model / packet["id"]
                outcome = await request(packet, model, folder, client)
                record(packet, model, outcome, str(folder))
                consecutive_errors = consecutive_errors + 1 if outcome["status"] == "provider_error" else 0
                if consecutive_errors >= 2:
                    save(root / (model + ".held.json"), {"time": now(), "reason": "Two consecutive provider/infrastructure errors; no retry or replacement", "last": str(folder)})
                    print(json.dumps({"alert": "model_route_held", "model": model, "evidence": str(folder)}), flush=True)
                    break

    await asyncio.gather(*(model_loop(model) for model in MODELS))
    save(root / "completion.json", {"time": now(), "recorded": len(rows),
        "planned_maximum": len(packets) * len(MODELS), "statuses": Counter(r["status"] for r in rows),
        "route_held": [m for m in MODELS if (root / (m + ".held.json")).exists()],
        "initial_input_screen_only": True, "tools_executed": 0})
    print(json.dumps({"finished": True, "rows": len(rows), "statuses": Counter(r["status"] for r in rows)}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "screen.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prepare(args.output) if args.prepare else asyncio.run(collect(args.output))


if __name__ == "__main__":
    main()
