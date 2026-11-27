"""Locate where exchanges stopped in a sealed socket-backed project store."""
import gzip
import hashlib
import io
import json

from swarmform.artifact_blobs import content_bytes


def socket_returns(case, manifest):
    def sealed(name):
        raw = (case / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest[name]:
            raise ValueError(f"Socket activity digest mismatch for {name}")
        return raw

    reg = json.loads(sealed("registration.json"))
    if reg["channel"] != "socket":
        raise ValueError("Socket activity requires a socket cohort")
    window = reg["cohort_deadline_seconds"]
    origin = json.loads(sealed("activation.json"))["unix"]
    workspace = json.loads(sealed("service.json"))["/workspace"]
    journal = content_bytes(workspace.get("/workspace/access.jsonl", ""), case / "reads/_service")
    calls = {}
    for actor in sorted(reg["entry_offsets_seconds"]):
        by_id = {}
        with gzip.GzipFile(fileobj=io.BytesIO(sealed(actor + ".jsonl.gz"))) as stream:
            for line in stream:
                event = json.loads(line)
                if event["kind"] == "tool_start":
                    by_id[event["call_id"]] = {"start": event["s"], "decision": event["decision_s"]}
                elif event["kind"] == "tool_result":
                    by_id[event["call_id"]]["end"] = event["s"]
        calls[actor] = by_id

    seeds = reg["manifest"]["initial_project_sha256"]
    last_digest = dict(seeds)
    writes, reads, visits = {}, [], []
    for number, raw in enumerate(journal.splitlines(), 1):
        entry = json.loads(raw)
        actor, op = entry["actor"], entry["request"]["operation"]
        when = entry["at_ns"] / 1e9 - origin
        if actor not in calls or not 0 <= when <= window:
            continue
        ids = [cid for cid, v in calls[actor].items() if v["start"] <= when <= v.get("end", -1)]
        cid = ids[0] if len(ids) == 1 else None
        when_returned = calls[actor][cid]["end"] if cid else float("inf")
        visit = dict(actor=actor, journal_line=number, seconds=when, call=cid)
        if op in ("read", "list") and when_returned <= window:
            visits.append(dict(**visit, operation=op, returned_s=when_returned))
        if op not in ("write", "read"):
            continue
        result = entry["result"]
        name, version, digest = result["name"], result["version"], result["sha256"]
        key = name, version, digest
        event = dict(**visit, name=name, version=version, sha256=digest)
        if op == "write":
            if cid is None:
                raise ValueError(f"Socket publication at line {number} has no matching native call")
            if digest != last_digest.get(name) and digest not in seeds.values():
                writes[key] = event
            last_digest[name] = digest
        elif key in writes and writes[key]["actor"] != actor and when_returned <= window:
            author = writes[key]
            reads.append(dict(**event, returned_s=when_returned, author=author["actor"],
                              write_line=author["journal_line"]))

    replies = [(r, w) for r in reads for w in writes.values()
               if w["actor"] == r["actor"] and calls[w["actor"]][w["call"]]["decision"] >= r["returned_s"]]
    returns = [(r, w, back) for r, w in replies for back in reads
               if back["actor"] == r["author"] and back["write_line"] == w["journal_line"]]
    opportunity = None
    if writes:
        first = next(iter(writes.values()))
        others = {}
        for actor, by_id in calls.items():
            if actor == first["actor"]:
                continue
            later_calls = (dict(call=cid, decision=v["decision"], returned_s=v["end"])
                           for cid, v in by_id.items()
                           if v["decision"] > first["seconds"] and v.get("end", window + 1) <= window)
            access = next((v for v in visits if v["actor"] == actor and v["journal_line"] > first["journal_line"]), None)
            others[actor] = dict(first_subsequent_store_request=access,
                                 first_subsequent_tool_decision=min(later_calls, key=lambda v: v["decision"], default=None))
        opportunity = dict(first_publication=first, other_accounts=others)

    if not writes:
        stage = "no_changed_publication"
    elif not reads:
        stage = "published_no_peer_download"
    elif not replies:
        stage = "download_no_later_publication_by_reader"
    elif not returns:
        stage = "later_publication_no_return_to_origin"
    else:
        stage = "return_download_for_content_review"
    strongest = returns or replies
    example = list(strongest[0]) if strongest else reads[:1]
    return dict(stage=stage, contact_opportunities=opportunity, publications=len(writes), peer_downloads=len(reads),
                read_to_later_write_candidates=len(replies), return_candidates=len(returns),
                first_publication_s=min((w["seconds"] for w in writes.values()), default=None),
                first_peer_download_s=min((r["returned_s"] for r in reads), default=None), first_example=example)
