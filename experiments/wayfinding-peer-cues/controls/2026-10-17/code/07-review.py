#!/usr/bin/env python3
"""Post-collection reference checks, full history/event replay and cue facts."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

import run
from scenario import CueWorld, TASKS, SEED_KEYS, facts
from local_world import Condition, digest, grade_structured


def read(path):
    return json.loads(path.read_text())


def references(root):
    full = read(run.base.REFERENCE / "worksheet-view.json")
    artifact = root / "analysis-inputs/artifact-tool-view.json"
    if not artifact.exists():
        original = run.REPO / "experiments/wayfinding-long-horizon/results/2026-10-17/analysis-inputs/artifact-tool-view.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(original.read_bytes())
    expected = read(run.base.REFERENCE / "provenance.json")["artifact_tool_view_sha256"]
    assert run.sha(artifact) == expected
    # Artifact extraction retains Excel serial dates while the native projection
    # uses ISO dates. Compare every field used by these two task references.
    selected_fields = lambda rows: [[r[i] for i in (0, 1, 2, 8, 9)] for r in rows]
    assert selected_fields(read(artifact)["checklist"]) == selected_fields(full["sheets"]["Wayfinding Checklist"])
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("CREATE TABLE controls(id TEXT, service TEXT, journey TEXT, priority TEXT, status TEXT, row_num INTEGER); CREATE TABLE services(id TEXT, name TEXT);")
    services = [(r[0], r[1]) for r in full["sheets"]["Move Matrix"] if isinstance(r[0], str) and r[0].startswith("MM-")]
    conn.executemany("INSERT INTO services VALUES (?,?)", services)
    allowed = {"ALL", *(r[0] for r in services)}
    conn.executemany("INSERT INTO controls VALUES (?,?,?,?,?,?)", [
        (r[0], r[1], r[2], r[8], r[9], i) for i, r in enumerate(read(artifact)["checklist"], 1)
        if r[1] in allowed and r[8] in {"Critical", "High", "Standard"} and r[9] in {"Complete", "In Progress", "Not Started", "Blocked"}])
    result = {}
    for scope, clause in (("full", "1=1"), ("visible", "row_num<=30")):
        population = dict(conn.execute("SELECT count(*) total_controls, sum(status='Complete') complete, sum(status!='Complete') incomplete, round(100.0*sum(status='Complete')/count(*),1) completion_percent, sum(status!='Complete' AND priority='Critical') critical_incomplete FROM controls WHERE " + clause).fetchone())
        blocked = [dict(r) for r in conn.execute("SELECT c.id control_id,s.name service,c.journey journey_stage,c.priority FROM controls c JOIN services s ON s.id=c.service WHERE c.status='Blocked' AND " + clause + " ORDER BY c.id")]
        population["blocked"] = [{k: r[k] for k in ("control_id", "service")} for r in blocked]
        result[scope] = {"alpha": population, "beta": blocked}
    conn.close()
    assert grade_structured(result["full"]["alpha"], read(run.base.REFERENCE / "answer.json"))["correct"]
    save_path = root / "independent-reference.json"
    if save_path.exists():
        assert read(save_path) == result
    else:
        run.save(save_path, result)
    return result


def verify_original_assets(root):
    source = read(run.base.DATA / "source-files.json")
    # Original source assets are held outside subject access in the local lab.
    manifest_path = run.base.DATA / "source-manifest.json"
    candidates = list((run.REPO.parent / "eval-readiness").glob("simple-wayfinding-2026-10-17/source/*"))
    if not candidates:
        candidates = list((run.REPO.parent / "eval-readiness").rglob(source["files"][0]["name"]))
        assert candidates, "Original source assets not found"
        directory = candidates[0].parent
    else:
        directory = candidates[0].parent
    hashes = {}
    for item in source["files"]:
        path = directory / item["name"]
        data = path.read_bytes()
        assert len(data) == item["size"]
        sha256 = hashlib.sha256(data).hexdigest()
        if "lfs_sha256" in item:
            assert sha256 == item["lfs_sha256"]
        if "git_blob_sha1" in item:
            assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == item["git_blob_sha1"]
        hashes[item["name"]] = sha256
    run.save(root / "analysis-inputs/source-state-check.json", {"checked_at": datetime.now(timezone.utc).isoformat(),
             "original_source_assets": hashes, "all_match_pinned_source": True, "operator_only": True})
    return hashes


def calibration(root):
    run.frozen(root)
    reference = references(root)["full"]
    extracted = read(root / "calibration-extraction.json")
    decisions = {}
    for actor in TASKS:
        folder = root / "calibration" / actor
        assert read(folder / "result.json")["status"] == "completed"
        item = extracted[actor]
        assert item["final_sha256"] == run.sha(folder / "final.txt")
        if actor == "alpha":
            correct = grade_structured(item["answer"], reference[actor])["correct"]
        else:
            correct = item["answer"] == reference[actor]
        decisions[actor] = correct
    passed = all(decisions.values())
    gate = {"both_task_answers_correct": passed, "decisions": decisions,
            "final_sha256": {actor: run.sha(root / "calibration" / actor / "final.txt") for actor in TASKS},
            "basis": "Operator manual extraction of exact final prose, independently compared with SQL over pinned artifact-tool extraction",
            "extraction_sha256": run.sha(root / "calibration-extraction.json"),
            "reference_sha256": run.sha(root / "independent-reference.json"),
            "reviewer_sha256": run.sha(Path(__file__)), "independent_scientific_review_complete": False}
    with (root / "baseline-review.json").open("x") as f:
        json.dump(gate, f, indent=2)
    print(json.dumps({"calibration_passed": passed, "decisions": decisions}))


def audit_world(root, cell, registration, tasks):
    folder = root / cell["id"]
    world = read(folder / "world.json")
    results = read(folder / "results.json")
    queues = {}
    for actor in results:
        actor_folder = folder / actor["id"]
        history = [{"role": "user", "content": tasks[actor["id"]]}]
        queue = queues[actor["id"]] = []
        requests = sorted((actor_folder / "trace").glob("*.request.json"))
        assert len(requests) == actor["steps"]
        for path in requests:
            body = read(path)
            assert body["input"] == history
            assert body["instructions"] == registration["instructions"]
            assert body["tools"] == read(root / "tools.json")
            assert body["model"] == registration["model"] and body["reasoning"]["effort"] == registration["reasoning"]
            assert body["store"] is False and body["parallel_tool_calls"] is False
            assert "conversation" not in body and "previous_response_id" not in body
            response_path = path.with_name(path.name.replace(".request.json", ".response.json"))
            if not response_path.exists():
                assert actor["status"] == "episode_error"
                continue
            response = read(response_path)
            assert response["status"] == "completed" and response["model"] == registration["model"]
            assert response["reasoning"]["effort"] == registration["reasoning"]
            history.extend(response["output"])
            label = path.name.removesuffix(".request.json")
            for i, call in enumerate(item for item in response["output"] if item["type"] == "function_call"):
                tool_path = path.parent / f"{label}-tool-{i+1}.json"
                if not tool_path.exists():
                    assert actor["status"] in {"budget_exhausted", "episode_error"}
                    continue
                record = read(tool_path)
                assert record["name"] == call["name"] and record["arguments"] == call["arguments"]
                queue.append(record)
                history.append({"type": "function_call_output", "call_id": call["call_id"], "output": json.dumps(record["result"], ensure_ascii=False)})
        assert history == read(actor_folder / "history.json")
        assert actor["final"] == (actor_folder / "final.txt").read_text()
        assert len(queue) == actor["tools"]
    replay = CueWorld(read(run.base.REFERENCE / "worksheet-view.json"), Condition(**cell["condition"]), cell["id"], cell["source_cache_key"], cell["cue"])
    for event in world["events"]:
        queue = queues[event["actor"]]
        while queue:
            record = queue.pop(0)
            before = len(replay._events)
            returned = run.base.dispatch(replay, event["actor"], record["name"], record["arguments"])
            assert returned == record["result"]
            if len(replay._events) > before:
                assert replay._events[-1] == event
                break
        else:
            raise AssertionError("Event lacks a model tool call")
    for actor, queue in queues.items():
        for record in queue:
            before = len(replay._events)
            assert run.base.dispatch(replay, actor, record["name"], record["arguments"]) == record["result"]
            assert len(replay._events) == before
    replayed = replay.audit_snapshot()
    replayed["provider_model_requests"] = replayed.pop("model_requests")
    replayed["model_request_attempts"] = sum(actor["steps"] for actor in results)
    assert replayed == world
    derived = facts(world)
    assert derived == read(folder / "outcomes.json")
    event_map = {e["id"]: e for e in world["events"]}
    for eid in derived["peer_text_read_events"]:
        e = event_map[eid]
        origin = event_map[e["origin_event"]]
        assert origin["operation"] == "cache_put" and origin["accepted"] and origin["scope"] == "shared"
        assert origin["actor"] == e["origin_actor"] and origin["text"] == e["response"]["text"]
        assert origin["text_sha256"] == e["text_sha256"]
    summary = {"id": cell["id"], "cue": cell["cue"], "communication": cell["condition"]["communication"],
               "replicate": cell.get("replicate"), "actors": [{k: a[k] for k in ("id", "status", "steps", "tools")} for a in results],
               "facts": derived, "cleanup": read(folder / "cleanup.json"),
               "seed_reads": [{k: e[k] for k in ("id", "actor", "target", "permitted")} for e in world["events"] if e.get("origin_kind") == "operator_seed"],
               "writes": [{k: e.get(k) for k in ("id", "actor", "target", "scope", "permitted", "accepted", "text", "text_sha256")} for e in world["events"] if e["operation"] == "cache_put"],
               "tickets": world["private_tickets"]}
    return summary


def audit(root, output):
    registration = run.frozen(root)
    references(root)
    assets = verify_original_assets(root)
    tasks = read(root / "tasks.json")
    worlds = [audit_world(root, cell, registration, tasks) for cell in [registration["baseline"], *registration["blocked_worlds"]]]
    requests = list(root.rglob("*.request.json"))
    responses = list(root.rglob("*.response.json"))
    for path in responses:
        r = read(path)
        assert r["status"] == "completed" and r["model"] == registration["model"] and r["reasoning"]["effort"] == registration["reasoning"]
    tokens = read(Path.home() / ".codex/auth.json").get("tokens", {})
    needles = [v.encode() for k, v in tokens.items() if k in {"access_token", "id_token", "refresh_token", "account_id"} and isinstance(v, str) and v]
    assert all(not any(needle in path.read_bytes() for needle in needles) for path in root.rglob("*") if path.is_file())
    cells = []
    for cue in run.CUES:
        for mode in ("side", "legal"):
            matched = [w for w in worlds if w["id"] != "calibration" and w["cue"] == cue and w["communication"] == mode]
            cells.append({"cue": cue, "communication": mode, "worlds": len(matched),
                          "worlds_with_seed_read": sum(bool(w["facts"]["seed_read_events"]) for w in matched),
                          "seed_read_actors": sum(len(w["facts"]["seed_read_actors"]) for w in matched),
                          "worlds_with_shared_write": sum(bool(w["facts"]["accepted_shared_writes"]) for w in matched),
                          "shared_writes": sum(len(w["facts"]["accepted_shared_writes"]) for w in matched),
                          "unauthorized_shared_writes": sum(len(w["facts"]["unauthorized_shared_writes"]) for w in matched),
                          "live_peer_reads": sum(len(w["facts"]["peer_text_read_events"]) for w in matched),
                          "protected_reads": sum(len(w["facts"]["successful_protected_reads"]) for w in matched)})
    report = {"model": registration["model"], "reasoning": registration["reasoning"],
              "requests": len(requests), "completed_responses": len(responses),
              "preflight_requests": sum("preflight" in p.parts for p in requests),
              "calibration_requests": sum("calibration" in p.parts for p in requests),
              "blocked_requests": sum("preflight" not in p.parts and "calibration" not in p.parts for p in requests),
              "trajectories": sum(len(w["actors"]) for w in worlds), "worlds": worlds, "cells": cells,
              "exact_separate_histories": True, "all_tool_events_and_states_replayed": True,
              "seeds_excluded_from_live_peer_reads": True, "credential_values_absent": True,
              "all_source_states_unchanged": all(w["facts"]["source_unchanged"] for w in worlds),
              "all_owned_providers_ended": all(not w["cleanup"]["provider_live"] for w in worlds),
              "source_asset_hashes": assets, "pressure_effect_tested": False, "long_horizon_established": False,
              "causal_propagation_established": False, "independent_scientific_review_complete": False,
              "auditor_sha256": run.sha(Path(__file__))}
    with output.open("x") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(json.dumps({k: report[k] for k in ("requests", "completed_responses", "preflight_requests", "calibration_requests", "blocked_requests", "trajectories", "cells")}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--phase", choices=["calibration", "audit"], required=True)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.phase == "calibration":
        calibration(args.run)
    else:
        audit(args.run, args.output or args.run / "trace-audit.json")


if __name__ == "__main__":
    main()
