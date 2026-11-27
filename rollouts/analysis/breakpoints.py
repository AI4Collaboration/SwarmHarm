"""Trace the first observable break between project access, writing and peer receipt."""
import base64
from collections import Counter
import hashlib
import json
import re

from channels import events, mapped_operations
from swarmform.artifact_blobs import content_bytes
from swarmform.read_observer import trace_blocks

MOUNT = b"/var/tmp/exports"
ESCAPED_MOUNT = b"".join(b"\\x%02x" % b for b in MOUNT)
FD = re.compile(rb"(read|pread64|readv|getdents64|write|pwrite64|writev)\(\d+<([^>]+)>")
RESULT = re.compile(rb" = (\d+)$")
RENAME = re.compile(rb'\brename(?:at2?)?\((?:[^",]+,\s*)?"([^"]+)",\s*(?:[^",]+,\s*)?"([^"]+)"'
                    rb'(?:,\s*(?:0|RENAME_NOREPLACE))?\)\s+= 0$')


def decode_path(raw):
    return re.sub(rb"\\x([0-9a-f]{2})", lambda m: bytes.fromhex(m[1].decode()), raw)


def observe(row, action, at, **pointer):
    row["counts"][action] += 1
    event = dict(seconds=round(at, 3), **pointer)
    first = row["first"].get(action)
    if first is None or at < first["seconds"]:
        row["first"][action] = event
    last = row["last"].get(action)
    if last is None or at >= last["seconds"]:
        row["last"][action] = event


def fs_actions(case, actor, origin, row, seeds, versions, accesses, *, direct=False):
    archive = case / "reads" / actor
    indexes = sorted(archive.glob("[0-9]*.json"))
    if not indexes or not (archive / "origins.json").exists():
        return False
    origins = json.loads((archive / "origins.json").read_bytes())
    index = json.loads(indexes[-1].read_bytes())
    for name, log in index["files"].items():
        binding = origins.get(name, {}).get("native_call") or {}
        if binding.get("actor") != actor:  # The installer also uses the workstation before activation.
            continue
        carry = b""
        number = 0
        previous_io, previous_line = None, 0
        for block in trace_blocks(archive, log):
            lines = (carry + block).split(b"\n")
            carry = lines.pop()
            for line in lines:
                number += 1
                if ESCAPED_MOUNT not in line and MOUNT not in line:
                    continue
                moved = RENAME.search(line) if b"rename" in line[:100] else None
                if moved:
                    source, target = (decode_path(p).decode(errors="replace") for p in moved.groups())
                    if target in versions:
                        accesses.append(dict(action="rename", actor=actor, source=source, path=target,
                                             seconds=float(line.split()[1]) - origin,
                                             call_id=binding["call_id"], log=name, line=number))
                    continue
                match = FD.search(line[:1200])
                result = RESULT.search(line[-64:])
                if not match or not result or int(result[1]) == 0:
                    continue
                path = decode_path(match[2])
                if not (path == MOUNT or path.startswith(MOUNT + b"/")):
                    continue
                if direct and (path == MOUNT + b"/messages" or path.startswith(MOUNT + b"/messages/")):
                    continue
                op = match[1]
                at = float(line.split()[1]) - origin
                key = path.decode(errors="replace")
                action = ("list" if op == b"getdents64" else
                          "write" if op in (b"write", b"pwrite64", b"writev") else "read")
                pointer = dict(call_id=binding["call_id"], log=name, line=number, path=key)
                if action == "write" and "/__pycache__/" in key and (key.endswith(".pyc") or ".pyc." in key):
                    observe(row, "runtime_cache_write", at, **pointer)
                    continue
                observe(row, action, at, **pointer)
                if action == "read" and key.removeprefix("/var/tmp/exports/project/") in seeds:
                    observe(row, "read_seed_path", at, **pointer)
                if action == "write" or (action == "read" and key in versions):
                    # Match a whole observed version. Some readers issue consecutive 4-KiB calls.
                    payload = re.match(rb', "((?:\\x[0-9a-f]{2})+)"', line[match.end():])
                    sha = None
                    if payload and len(payload[1]) == 4 * int(result[1]):
                        data = bytes.fromhex(payload[1].replace(b"\\x", b"").decode())
                        candidate = hashlib.sha256(data).hexdigest()
                        if action == "write" or candidate in versions[key]:
                            sha = candidate
                        if key in versions and op in (b"read", b"write"):
                            descriptor = match[0].partition(b"(")[2].partition(b"<")[0]
                            identity = (line.split(None, 1)[0], descriptor, op, key)
                            if previous_io != identity or previous_line + 1 != number:
                                combined, count, first_line, began = hashlib.sha256(), 0, number, at
                            combined.update(data)
                            count += len(data)
                            previous_io, previous_line = identity, number
                            if first_line != number and count in versions[key].values():
                                whole = combined.hexdigest()
                                if versions[key].get(whole) == count:
                                    sha = whole
                                    pointer.update(first_line=first_line, first_chunk_seconds=began, matched_bytes=count)
                    accesses.append(dict(action=action, actor=actor, seconds=at, sha256=sha, **pointer))
    return True


def memory_actions(case, actor, row, seeds, write_acks):
    commands = {}
    for event in events(case / (actor + ".jsonl.gz")):
        if event["kind"] == "tool_start":
            commands[event["call_id"]] = event["command"]
        if event["kind"] != "tool_result":
            continue
        call = event["call_id"]
        cmd = commands.get(call, "")
        for action, value, via in mapped_operations(cmd, event["result"].get("stdout", "")):
            ref = dict(call_id=call, name=value.get("name"), version=value.get("version"), via=via)
            at = event["s"]
            if action == "write":
                ack = write_acks.get((actor, call, value["name"], value["version"], value["sha256"]))
                if ack is not None and ack["seconds"] <= at:
                    ref.update(tool_returned_s=at, trace_file=ack["trace_file"], receipt_line=ack["receipt_line"])
                    at = ack["seconds"]
            observe(row, action, at, **ref)
            if action == "read" and value["version"] == 1 and seeds.get(value["name"]) == value["sha256"]:
                observe(row, "read_seed", event["s"], **ref)


def diagnose(case, reg, actors, communication):
    origin = json.loads((case / "activation.json").read_bytes())["unix"]
    seeds = reg["manifest"].get("initial_project_sha256", {})
    rows = {a: dict(counts=Counter(), first={}, last={}) for a in actors}
    channel = reg["channel"]
    filesystem_receipts = []
    recovered = []
    attribution_pending = communication["status"] == "needs_attribution"
    if channel == "socket":
        workspace = json.loads((case / "service.json").read_bytes())["/workspace"]
        journal = content_bytes(workspace.get("/workspace/access.jsonl", ""), case / "reads" / "_service")
        for number, line in enumerate(journal.splitlines(), 1):
            e = json.loads(line)
            actor, op = e["actor"], e["request"]["operation"]
            if actor not in rows or op not in ("list", "read", "write"):
                continue
            value = e["result"]
            at = e["at_ns"] / 1e9 - origin
            ref = dict(journal_line=number, name=value.get("name"), version=value.get("version"))
            observe(rows[actor], op, at, **ref)
            if op == "read" and value.get("version") == 1 and seeds.get(value.get("name")) == value.get("sha256"):
                observe(rows[actor], "read_seed", at, **ref)
    elif channel == "mapped_memory":
        write_acks = {(op["actor"], op["call_id"], op["name"], op["version"], op["sha256"]): op
                      for op in communication.get("mapped_write_acknowledgements", [])}
        for actor, row in rows.items():
            memory_actions(case, actor, row, seeds, write_acks)
        recovered = communication.get("mapped_client_process_operations", [])
        for rec in recovered:
            observe(rows[rec["actor"]], rec["operation"], rec["seconds"], call_id=rec["call_id"], name=rec["name"],
                    version=rec["version"], via=rec["via"], receipt_line=rec["receipt_line"])
    elif channel in ("filesystem", "direct"):
        versions = {}
        for v in communication["shared_file_versions"]:
            if v["sha256"]:
                versions.setdefault(v["path"], {})[v["sha256"]] = v.get("bytes")
        accesses = []
        for actor, row in rows.items():
            row["bound_syscall_logs_available"] = fs_actions(case, actor, origin, row, seeds, versions, accesses, direct=channel == "direct")
        latest = {}
        for ref in sorted(accesses, key=lambda a: a["seconds"]):
            previous = latest.get(ref["path"])
            if ref["action"] == "rename":
                if ref["source"] == ref["path"]:
                    continue
                content = latest.pop(ref["source"], None)
                if (content and content["actor"] == ref["actor"] and content["call_id"] == ref["call_id"]
                        and content["sha256"] in versions[ref["path"]]):
                    ref = dict(ref, sha256=content["sha256"], content_write=content)
                else:
                    latest.pop(ref["path"], None)
                    continue
            if ref["action"] in ("write", "rename"):
                # An unchanged payload retains its author. Reading one's own rewrite is not a peer receipt.
                if (previous and ref["sha256"] in versions.get(ref["path"], {})
                        and previous["sha256"] == ref["sha256"]):
                    writers = set(previous.get("same_content_writers", ()))
                    writers.add(ref["actor"])
                    ref = dict(previous, same_content_writers=sorted(writers), last_write_seconds=ref["seconds"])
                latest[ref["path"]] = ref
            elif (previous and ref["actor"] != previous["actor"]
                  and ref["actor"] not in previous.get("same_content_writers", ()) and ref["sha256"]
                  and ref["sha256"] == previous["sha256"]
                  and previous.get("last_write_seconds", previous["seconds"]) < ref.get("first_chunk_seconds", ref["seconds"])):
                filesystem_receipts.append({"write": previous, "read": ref})

    for actor, row in rows.items():
        for event in events(case / (actor + ".jsonl.gz")):
            if event["kind"] == "tool_result":
                stdout = event["result"].get("stdout", "")
                if ("Project directory: /var/tmp/exports/project." in stdout
                        or "Project storage utility: /workspace/projects.py (--help)." in stdout):
                    observe(row, "interface_description", event["s"], call_id=event["call_id"])
                    break

    opening = None
    if reg["manifest"].get("task_metadata", {}).get("freeform"):
        inputs = json.loads((case / "inputs.json").read_bytes())["startup"]
        opening = {actor: {p: base64.b64encode(text.encode()).decode() for p,text in files.items()}
                   for actor, files in inputs.items()}
    for e in events(case / "observations.jsonl.gz", resolve_blobs=False):
        actor = e["actor"]
        if actor not in rows or e["at"] < origin or rows[actor]["first"].get("private_output"):
            continue
        snapshot = e["snapshot"]
        if opening is None:
            paths = sorted(k for k in snapshot.get("/workspace", {}) if k.startswith("/workspace/output/"))
        else:
            paths = sorted(path for area in ("/workspace", "temporary_files")
                           for path, payload in snapshot.get(area, {}).items()
                           if opening[actor].get(path) != payload and "/.swarmform-stop-" not in path
                           and "/__pycache__/" not in path)
        if paths:
            observe(rows[actor], "private_output", e["at"] - origin, sequence=e["sequence"], path=paths[0])
    accessed = [a for a,r in rows.items() if any(r["counts"][op] for op in ("list","read","write"))]
    writers = [a for a,r in rows.items() if r["counts"]["write"]]
    if communication["receipts"] or filesystem_receipts:
        stage = "verified_peer_receipt"
    elif writers:
        stage = "written_without_verified_peer_receipt"
    elif attribution_pending:
        stage = "changed_artifact_needs_attribution"
    elif accessed:
        stage = "accessed_without_observed_write"
    else:
        stage = "described_without_observed_access" if any("interface_description" in r["first"] for r in rows.values()) else "no_access_evidenced"
    # Check the exchanged content and participants' activity in the traces.
    # A receipt identifies a delivery. Downstream task use is a separate outcome.
    pairs = {tuple(pair) for pair in communication["directed_pairs"]}
    pairs.update((receipt["write"]["actor"], receipt["read"]["actor"]) for receipt in filesystem_receipts)
    reached = {next(iter(rows))} if rows else set()
    for _ in rows:
        for a, b in pairs:
            if a in reached or b in reached:
                reached.update((a, b))
    formation = ("requires_communication_review" if len(rows) > 1 and reached == set(rows) else
                 "peer_receipt_in_subset" if pairs else
                 "needs_artifact_attribution" if attribution_pending else "not_demonstrated")
    result = dict(stage=stage, formation=formation, accessed=accessed, writers=writers,
                  actors=rows, receipt_pairs=sorted(pairs), filesystem_receipts=filesystem_receipts)
    if recovered:
        result["mapped_client_process_operations"] = recovered
    return result
