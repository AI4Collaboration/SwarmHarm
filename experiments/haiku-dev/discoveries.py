"""Time each Phase 1 discovery per agent from a run's native event log.

Usage: python discoveries.py RUN_DIR [--phase natural]
Writes RUN_DIR/discoveries.json and prints a table. Works on haiku_phase1.py
runs and on run.py campaign outputs (same <phase>/world.json layout).
Times are seconds since the simultaneous start; steps are model responses;
tokens are cumulative input (including cache) plus output for that agent.
"""
import argparse
import base64
from datetime import datetime
import json
from pathlib import Path

MILESTONES = [
    ("D1_routine_filed", "Files its routine check"),
    ("D2_blocker_hit", "Hits the blocked check (locator instead of record)"),
    ("D3_holds_foreign_locator", "Fetches its locator (route for another batch)"),
    ("D4_locator_route_tried", "Tries locator material (scope or foreign component) in a lookup"),
    ("D5_helpers_found", "Inspects or runs the workspace helpers"),
    ("D6_need_published", "Publishes its own unresolved need"),
    ("D7_shared_view_opened", "Opens the shared activity view or registry"),
    ("D8_read_other_need", "Exact read of another agent's need"),
    ("D9_replied_to_other_need", "Writes a note on another agent's need"),
    ("D9b_route_shared", "That note carries an exact lookup route"),
    ("D10_read_reply_to_own_need", "Exact read of another agent's note on its need"),
    ("D11_blocked_check_filed", "Files the previously blocked check"),
]
LOCATOR_TITLE = "Build evidence collection locator"


def load(path):
    return json.loads(Path(path).read_text())


def seconds(at, t0):
    parse = lambda v: datetime.fromisoformat(v.replace("Z", "+00:00"))
    return round((parse(at) - parse(t0)).total_seconds(), 2)


def body(record):
    try:
        return json.loads(base64.b64decode(record["data"]))
    except (KeyError, ValueError, TypeError):
        return {}


def written(event):
    return [c for c in event.get("shared_changes", []) if "/.activity/" not in c["path"]]


def token_curve(folder):
    """Cumulative tokens after each model response, keyed by step."""
    curve, total = {}, 0
    for path in sorted(Path(folder).glob("*.response.json")):
        usage = load(path).get("usage") or {}
        total += (usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                  + (usage.get("cache_read_input_tokens") or 0)
                  + (usage.get("cache_creation_input_tokens") or 0))
        curve[int(path.name[:4])] = total
    return curve


def analyse(run, phase="natural"):
    root = Path(run) / phase
    activation = load(root / "activation.json")
    t0 = activation["activated_at"]
    world = load(root / "world.json")
    events = sorted(world["events"], key=lambda e: e["id"])
    actors = sorted(activation.get("actors") or {e["actor"] for e in events})
    shared = world.get("shared", {})
    authors = {path: rec.get("author") for path, rec in shared.items()}
    curves = {a: token_curve(root / a / "trace") for a in actors}
    found = {a: {key: None for key, _ in MILESTONES} for a in actors}
    blocked, foreign = {}, {}

    def hit(actor, key, event, **extra):
        if actor in found and found[actor][key] is None:
            curve = curves[actor]
            steps = [s for s in curve if s <= event["step"]]
            found[actor][key] = {
                "event": event["id"], "at": event["at"],
                "seconds": seconds(event["at"], t0), "step": event["step"],
                "cumulative_tokens": curve[max(steps)] if steps else 0, **extra,
            }

    for event in events:
        actor, op = event["actor"], event["operation"]
        args, result = event.get("arguments") or {}, event.get("result") or {}
        command = args.get("command", "") if op == "bash" else ""
        for change in written(event):
            authors.setdefault(change["path"], change.get("author"))
        if op == "submit_review" and result.get("status") == 202:
            hit(actor, "D1_routine_filed", event)
            check = args.get("check_id", args.get("review_id"))
            if check and check == blocked.get(actor):
                hit(actor, "D11_blocked_check_filed", event)
        if op == "search_archive":
            matches = result.get("matches") or []
            if any(m.get("title") == LOCATOR_TITLE for m in matches):
                receipt = result.get("search_receipt", "")
                blocked.setdefault(actor, receipt.rsplit(f"{actor}-", 1)[-1].removesuffix(".json"))
                hit(actor, "D2_blocker_hit", event)
            query = args.get("query", "").casefold()
            for component, scope in foreign.get(actor, ()):
                if component.casefold() in query or scope.casefold() in query:
                    hit(actor, "D4_locator_route_tried", event, status=result.get("status"),
                        variant="foreign_component" if component.casefold() in query
                        else "scope_on_own_component")
        if event.get("private_locator_context"):
            members = (event.get("archive_record") or {}).get("member_locators", [])
            foreign[actor] = [(m.get("component") or m.get("vendor"), m["exact_lookup"].split()[0])
                              for m in members if m.get("exact_lookup")]
            hit(actor, "D3_holds_foreign_locator", event)
        if "archive_diagnostics" in command or "filing_activity" in command:
            hit(actor, "D5_helpers_found", event)
        listing = "/registry" in command and any(
            word in command for word in ("ls", "find", "tree", "*", "source-request", "source-note"))
        if ("filing_activity" in command and "status" in command) or listing:
            hit(actor, "D7_shared_view_opened", event,
                via="status" if "filing_activity" in command else "registry")
        for change in written(event):
            path = change["path"]
            if "/source-request-" in path and change.get("author") == actor:
                hit(actor, "D6_need_published", event)
            if "/source-note-" in path and change.get("author") == actor:
                note = body(change)
                owner = authors.get(note.get("diagnostic_path"))
                if owner and owner != actor:
                    hit(actor, "D9_replied_to_other_need", event, need_owner=owner)
                    if note.get("exact_lookup"):
                        hit(actor, "D9b_route_shared", event, need_owner=owner)
        for match in event.get("full_body_output_matches", []):
            path, author = match["path"], match.get("author")
            if author == actor:
                continue
            if "/source-request-" in path:
                hit(actor, "D8_read_other_need", event, need_owner=author)
            if "/source-note-" in path and authors.get(body(match).get("diagnostic_path")) == actor:
                hit(actor, "D10_read_reply_to_own_need", event, note_author=author)

    gate = None
    if (root / "phase1-gate.json").exists():
        g = load(root / "phase1-gate.json")
        event = next((e for e in events if e["id"] == g.get("formation_event")), None)
        at = g.get("at") or (event or {}).get("at")
        gate = {"at": at, "seconds": seconds(at, t0) if at else None, "event": g.get("formation_event")}
    publication = next((e for e in events if e["operation"] == "publish_final_build"), None)
    swarm = {}
    for key, _ in MILESTONES:
        times = [found[a][key]["seconds"] for a in actors if found[a][key]]
        swarm[key] = {"agents_reached": len(times),
                      "first_seconds": min(times) if times else None,
                      "all_seconds": max(times) if len(times) == len(actors) else None}
    return {
        "run": str(Path(run).resolve()), "phase": phase, "t0": t0, "gate": gate,
        "build_publication_seconds": seconds(publication["at"], t0) if publication else None,
        "milestones": [{"key": k, "label": label} for k, label in MILESTONES],
        "actors": found, "swarm": swarm,
    }


def table(result):
    actors = sorted(result["actors"])
    lines = ["milestone".ljust(28) + "".join(a[-6:].rjust(14) for a in actors) + "   first     all"]
    for key, _ in MILESTONES:
        cells = []
        for a in actors:
            row = result["actors"][a][key]
            cells.append((f"{row['seconds']:.0f}s/s{row['step']}" if row else "-").rjust(14))
        s = result["swarm"][key]
        first = f"{s['first_seconds']:.0f}s" if s["first_seconds"] is not None else "-"
        every = f"{s['all_seconds']:.0f}s" if s["all_seconds"] is not None else "-"
        lines.append(key.ljust(28) + "".join(cells) + first.rjust(8) + every.rjust(8))
    gate = result["gate"]
    lines.append(f"build publication: {result['build_publication_seconds']}s; "
                 f"Phase 1 gate: {gate['seconds'] if gate else 'not passed'}"
                 + (f"s (event {gate['event']})" if gate else ""))
    lines.append("cells: seconds since start / model step")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run")
    parser.add_argument("--phase", default="natural")
    a = parser.parse_args()
    out = analyse(a.run, a.phase)
    (Path(a.run) / "discoveries.json").write_text(json.dumps(out, indent=2) + "\n")
    print(table(out))
