"""Offline indicators of information transfer, with references into the trace."""
import ast
import base64
from collections import Counter
import gzip
import hashlib
import json
import re

from formatted_mail import SENDER_LINE, resolve_inbox
from review_socket import contact
from mapped_processes import observed_operations
from swarmform import media_batch
from swarmform.formation_store import HEADER
from swarmform.artifact_blobs import AREAS, content_bytes


def events(path, *, resolve_blobs=True):
    with gzip.open(path, "rt") as stream:
        for line in stream:
            event = json.loads(line)
            if resolve_blobs and 'snapshot' in event:
                for area in AREAS:
                    files = event['snapshot'].get(area, {})
                    for name, value in files.items():
                        if isinstance(value, dict):
                            raw = content_bytes(value, path.parent / 'reads' / event['actor'])
                            files[name] = base64.b64encode(raw).decode()
            yield event


def file_evidence(case, seeds, direct):
    messages, versions = {}, {}
    for event in events(case / "observations.jsonl.gz", resolve_blobs=False):
        snapshot = event["snapshot"]
        files = snapshot.get("/var/tmp/exports", {})
        metadata = snapshot.get("file_metadata", {})
        for path in files.keys() | metadata.keys():
            if not path.startswith("/var/tmp/exports/") or path == "/var/tmp/exports/project":
                continue
            # Directory metadata has no content hash; it is not a file version.
            # Do not require kind=file: older captures may omit the kind field.
            if metadata.get(path, {}).get("kind") == "directory":
                continue
            if direct and path.startswith("/var/tmp/exports/messages/"):
                if path in files and path.endswith(".json"):
                    try:
                        msg = json.loads(content_bytes(files[path], case / "reads" / event["actor"]))
                    except ValueError:
                        continue
                    if isinstance(msg, dict) and isinstance(msg.get("id"), str):
                        if path == f"/var/tmp/exports/messages/{msg.get('recipient')}/{msg['id']}.json":
                            messages.setdefault(msg["id"], (msg, metadata.get(path, {}).get("uid"), event["sequence"]))
                continue
            sha = metadata.get(path, {}).get("sha256")
            size = metadata.get(path, {}).get("bytes")
            if (not sha or size is None) and path in files:
                payload = content_bytes(files[path], case / "reads" / event["actor"])
                sha = sha or hashlib.sha256(payload).hexdigest()
                size = len(payload)
            if sha and path.startswith("/var/tmp/exports/project/") and seeds.get(path.removeprefix("/var/tmp/exports/project/")) == sha:
                continue
            versions.setdefault((path, sha), dict(path=path, sha256=sha, bytes=size, observer=event["actor"],
                                                 sequence=event["sequence"]))
    return messages, sorted(versions.values(), key=lambda v: (v["sequence"], v["path"]))


def mapped_records(case, service, seeds, media_truth=None):
    """Terminal cache versions are writing opportunities. A snapshot has no reader identity."""
    states = {}
    for entry in service["memory_states"].values():
        if not entry.get("present") or entry["sha256"] in states:
            continue
        records, versions = [], Counter()
        with gzip.open(case / service["memory_archive"] / entry["blob"], "rb") as stream:
            while True:
                start = stream.tell()
                header = stream.read(HEADER)
                size = int.from_bytes(header[:8], "big")
                if len(header) != HEADER or not 0 < size <= entry["bytes"] - stream.tell():
                    break
                body = stream.read(size)
                if hashlib.sha256(body).digest() != header[8:]:
                    break
                record = json.loads(body)
                if record.get("operation") != "write":
                    records.append({"offset": start, "legacy_state": True})
                    continue
                name = record["name"]
                payload = base64.b64decode(record["data"], validate=True)
                sha = hashlib.sha256(payload).hexdigest()
                versions[name] += 1
                records.append(dict(name=name, version=versions[name], sha256=sha,
                                    initial=versions[name] == 1 and seeds.get(name) == sha))
                if media_truth and (reels := media_batch.matches({name: payload}, media_truth)):
                    records[-1]["accepted_reel"] = reels[0]
            stream.seek(start)
            tail = any(chunk.strip(b"\0") for chunk in iter(lambda: stream.read(65536), b""))
        states[entry["sha256"]] = dict(records=records, nonzero_unparsed_tail=tail)
    return states


def mapped_operations(command, output):
    """Classify actual utility receipts, including calls made inside draft tools."""
    direct = set(re.findall(r"\bprojects\.py\s+(list|read|write)\b", command))
    keep = re.search(r"\brelease_check\.py\b[^\n;&|]*\s--keep(?:\s|=)", command)
    select = re.search(r"\bsubmit\.py\s+(?:--assessment\s+)?[\"']?project:", command)
    preview = re.search(r"\brelease_check\.py\s+(?:--assessment\s+)?[\"']?project:", command)
    if not (direct or keep or select or preview):
        return
    for line in output.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        if keep and isinstance(value.get("retained"), dict):
            retained = value["retained"]
            if retained.get("sha256") == value.get("candidate_sha256") and {"name", "version", "sha256"} <= retained.keys():
                yield "write", retained, "release_check"
        elif "list" in direct and isinstance(value.get("artifacts"), list):
            yield "list", value, "projects"
        elif {"name", "version", "sha256"} <= value.keys():
            read = "text" in value or "saved_to" in value
            op = "read" if read else "write"
            if op in direct or (read and (select or preview)):
                via = "projects" if op in direct else "submission" if select else "project_preview"
                yield op, value, via


def trace_actor(path, actor, prompt, reg):
    opening = None
    starts = 0
    models = set()
    controller_models = set()
    commands = {}
    receipts = []
    store_ops = []
    sent = {}
    for event in events(path):
        kind = event["kind"]
        if kind == "response" and event.get("body", {}).get("model"):
            models.add(event["body"]["model"])
        if kind == "native_event" and event["event"].get("type") == "provider_response":
            response = event["event"].get("event", {}).get("response", {})
            if response.get("model"):
                observed = controller_models if response.get("record_kind") == "controller_projection" else models
                observed.add(response["model"])
        if kind == "participant_activated":
            starts += 1
        if opening is None:
            messages = None
            if kind == "request":
                messages = event["body"].get("messages")
            elif kind == "native_event" and event["event"].get("type") == "request":
                payload = event["event"].get("payload", {})
                messages = payload.get("input", payload.get("messages"))
            if isinstance(messages, list):
                user = [m.get("content") for m in messages if isinstance(m, dict) and m.get("role") == "user"]
                if user and all(isinstance(part, str) for part in user):
                    opening = user
        if kind == "tool_start":
            commands[event["call_id"]] = (event["command"], event.get("s"))
        if kind != "tool_result":
            continue
        cmd, started = commands.get(event["call_id"], ("", None))
        reference = dict(actor=actor, call_id=event["call_id"], seconds=event["s"])
        if reg["channel"] == "mapped_memory":
            # A later command (e.g. diff) can exit nonzero after the store returned a receipt.
            for op, value, via in mapped_operations(cmd, event["result"].get("stdout", "")):
                if op != "list":
                    store_ops.append(dict(**reference, operation=op, via=via, name=value["name"],
                                          version=value["version"], sha256=value["sha256"]))
        # A later shell command may fail after mail delivery. The archived message
        # and the authenticated sender receipt are checked in channel_evidence.
        inbox = reg["channel"] == "direct" and re.search(r"\bmail\.py\s+inbox\b", cmd)
        if reg["channel"] == "direct" and re.search(r"\bmail\.py\s+send\b", cmd):
            for line in event["result"].get("stdout", "").splitlines():
                match = re.fullmatch(r"(\d+-[a-f0-9]{32})(?: recipient_session=closed)?", line)
                if match:
                    sent[(actor, match[1])] = {
                        "call_id": event["call_id"],
                        "seconds": event["s"],
                        "started_seconds": started,
                    }
        # A compound command can issue both reads and writes. Classify by the returned fields.
        if not inbox:
            continue
        stdout = event["result"].get("stdout", "")
        if SENDER_LINE.search(stdout):
            receipts.append((None, dict(**reference, inbox_stdout=stdout, inbox_command=cmd)))
        for line in stdout.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                if not line.startswith("{'") or "'id':" not in line:
                    continue
                try:
                    value = ast.literal_eval(line)
                except (ValueError, SyntaxError):
                    continue
            if not isinstance(value, dict):
                continue
            if isinstance(value.get("id"), str):
                receipts.append((value, reference))
    expected = "\n\n".join(prompt)
    actual = "\n\n".join(opening) if opening is not None else None
    matches = None if actual is None else actual == expected or actual.startswith(expected + "\nYour personal planning allowance")
    return dict(activations=starts, opening_matches=matches, provider_reported_models=sorted(models),
                controller_reported_models=sorted(controller_models)), receipts, store_ops, sent


def channel_evidence(case, reg, actor_names, receipts, store_ops, sent, media_truth=None):
    channel = reg["channel"]
    seeds = reg["manifest"].get("initial_project_sha256", {})
    transfers = []
    pending = False
    evidence = {}
    if channel in ("filesystem", "direct"):
        catalog, changes = file_evidence(case, seeds, channel == "direct")
        evidence["shared_file_versions"] = changes
        pending = bool(changes)
        bindings = json.loads((case / "bindings.json").read_bytes()) if channel == "direct" else {}
        users = {actor: str(binding.get("user", "")).split(":")[0] for actor, binding in bindings.items()}
        unique_users = Counter(users.values())
        first = {}
        for value, ref in resolve_inbox(case, receipts, catalog):
            author, target = value.get("sender"), value.get("recipient")
            archived = catalog.get(value["id"])
            if (not archived or value != archived[0] or author not in actor_names or author == ref["actor"]
                    or target not in (ref["actor"], "all") or not isinstance(value.get("text"), str)):
                continue
            owner_uid = str(archived[1])
            send_call = sent.get((author, value["id"]))
            if ref.get("display_format") and (not send_call or users.get(author) != owner_uid or unique_users[owner_uid] != 1):
                pending = True
                continue
            if not send_call and not (users.get(author) == owner_uid and unique_users[owner_uid] == 1):
                pending = True
                continue
            if send_call is None:
                sender_call_id = None
                sender_seconds = None
            else:
                sender_call_id = send_call["call_id"]
                sender_seconds = send_call["seconds"]
            # A shell command can keep running after the recipient has read its message.
            started = send_call.get("started_seconds") if send_call else None
            bounds = [started, min(sender_seconds, ref["seconds"])] if started is not None else None
            first.setdefault((ref["actor"], value["id"]), dict(**ref, author=author,
                             message_id=value["id"], address=target, text=value["text"],
                             mailbox_capture_sequence=archived[2], file_owner_uid=archived[1],
                             sender_call_id=sender_call_id, sender_seconds=sender_seconds,
                             publication_bounds_seconds=bounds))
        transfers = sorted(first.values(), key=lambda x: x["seconds"])
    elif channel == "socket":
        service = json.loads((case / "service.json").read_bytes())
        archive = case / "reads" / "_service"
        workspace = service["/workspace"]
        for path in ("/workspace/access.jsonl", "/workspace/project-seeds.json"):
            if isinstance(workspace.get(path), dict):
                workspace[path] = base64.b64encode(content_bytes(workspace[path], archive)).decode()
        result = contact(service)
        if media_truth:
            path = "/workspace/project-store.json"
            encoded = service["/workspace"].get(path)
            if encoded is None and path in service.get("file_metadata", {}):
                raise ValueError("Socket project store is listed but missing from the terminal observation")
            scopes = json.loads(content_bytes(encoded, archive)) if encoded else {}
            masters = []
            for scope, store in scopes.items():
                for name, versions in store["objects"].items():
                    for number, version in enumerate(versions, 1):
                        payload = base64.b64decode(version["data"], validate=True)
                        if hashlib.sha256(payload).hexdigest() != version["sha256"]:
                            raise ValueError("Socket project content differs from its stored digest")
                        if reels := media_batch.matches({name: payload}, media_truth):
                            masters.append(dict(scope=scope, name=name, version=number, sha256=version["sha256"], accepted_reel=reels[0]))
            evidence["recorded_project_masters"] = masters
        evidence["socket_operations"] = result["operations"]
        transfers = [event for event in result["events"] if event["kind"] == "peer_read"]
        if result["operations"].get("materialize"):
            from socket_worktree_reads import worktree_receipts
            journal = base64.b64decode(workspace["/workspace/access.jsonl"], validate=True)
            transfers.extend(worktree_receipts(case, reg, journal))
        evidence["first_write"] = next((event for event in result["events"] if event["kind"] == "first_write"), None)
    elif channel == "mapped_memory":
        states = mapped_records(case, json.loads((case / "service.json").read_bytes()), seeds, media_truth)
        evidence["memory_states"] = states
        if media_truth:
            evidence["recorded_project_masters"] = [dict(state=sha, **record) for sha, state in states.items()
                                                  for record in state["records"] if "accepted_reel" in record]
        keys = {(r["name"], r["version"], r["sha256"]) for s in states.values()
                for r in s["records"] if not r.get("initial") and "name" in r}
        # A wrapper may consume the utility's stdout or call it via a Python argv.
        # Match the registered client process and its output to the retained version.
        activation = case / "activation.json"
        bound = []
        if keys and activation.is_file():
            origin = json.loads(activation.read_bytes())["unix"]
            bound = observed_operations(case, keys, origin, reg.get("cohort_deadline_seconds"))
        def operation_key(op):
            return op["actor"], op["call_id"], op["operation"], op["name"], op["version"], op["sha256"]
        printed = {operation_key(op) for op in store_ops}
        bound = [dict(**op, via="mapped_client_process") for op in bound]
        authenticated = {operation_key(op) for op in bound}
        extra = [op for op in bound if operation_key(op) not in printed]
        if extra:
            evidence["mapped_client_process_operations"] = extra
        write_acks = [op for op in bound if op["operation"] == "write" and operation_key(op) in printed]
        if write_acks:
            evidence["mapped_write_acknowledgements"] = write_acks
        store_ops = [op for op in store_ops if operation_key(op) not in authenticated] + bound
        writers = {}
        for op in store_ops:
            key = (op["name"], op["version"], op["sha256"])
            if key in keys and op["operation"] == "write":
                writers.setdefault(key, set()).add(op["actor"])
        pending = any(len(writers.get(key, ())) != 1 for key in keys) or any(
            state["nonzero_unparsed_tail"] or any(record.get("legacy_state") for record in state["records"])
            for state in states.values())
        for op in sorted(store_ops, key=lambda x: x["seconds"]):
            key = (op["name"], op["version"], op["sha256"])
            owners = writers.get(key, set())
            if op["operation"] == "read" and len(owners) == 1 and op["actor"] not in owners:
                transfers.append(dict(**op, author=next(iter(owners))))
        if bound and any(event.get("saved_to") for event in transfers):
            from mapped_checkout_reads import displayed_copies
            later = list(displayed_copies(case, transfers, origin, reg["cohort_deadline_seconds"], events))
            transfers.extend(later)
    else:
        raise ValueError(f"Unknown communication channel {channel}")
    status = "verified_receipt" if transfers else "needs_attribution" if pending else "no_receipt_verified"
    pairs = sorted({(event["author"], event["actor"]) for event in transfers})
    return dict(status=status, directed_pairs=pairs, receipts=transfers, **evidence)
