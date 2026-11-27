"""Replay the returned excerpts underlying a content-reviewed SwarmForm cohort."""
import argparse
import base64
from copy import deepcopy
import gzip
import hashlib
import io
from itertools import groupby
import json
import re
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
from codex_evidence import mcp_output_text
from formatted_mail import mailbox_files_read
from breakpoints import decode_path
from mapped_processes import EXEC, HEX_STRING, client_receipts, log_lines, unhex
from swarmform.artifact_blobs import content_bytes
from swarmform.formation_store import HEADER


def study_rows(study):
    yield from study["cohorts"]
    yield from study.get("ultrafast_validation", {}).get("cohorts", ())
    yield from study.get("release_source_matrix", {}).get("in_progress_registration_cohorts", [])
    yield from study.get("current_matrix", {}).get("reviewed_cohorts", [])
    if study.get("same_input_followup"):
        yield from study_rows(study["same_input_followup"])
    for field in ("completed_input_revisions", "same_input_followups"):
        for child in study.get(field, []):
            yield from study_rows(child)


def native_calls(case, manifest, actor, wanted):
    filename = actor + ".jsonl.gz"
    path = case / filename
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest[filename]:
        raise ValueError(f"Transcript digest mismatch for {actor}")
    starts = {}
    results = {}
    with gzip.open(path, "rt") as stream:
        for line in stream:
            event = json.loads(line)
            call = event.get("call_id")
            if call not in wanted:
                continue
            if event["kind"] == "tool_start":
                starts[call] = {"s": event["s"], "decision_s": event["decision_s"]}
            elif event["kind"] == "tool_result":
                results[call] = event
    return starts, results


def socket_transfer(case, manifest, delivery, sender, reader, reference):
    service = (case / "service.json").read_bytes()
    if hashlib.sha256(service).hexdigest() != manifest["service.json"]:
        raise ValueError("Socket journal digest mismatch")
    encoded = json.loads(service)["/workspace"]["/workspace/access.jsonl"]
    lines = content_bytes(encoded, case / "reads" / "_service").splitlines()
    if not 1 <= reference["write_line"] < reference["read_line"] <= len(lines):
        raise ValueError("Invalid socket journal offsets")
    written = json.loads(lines[reference["write_line"] - 1])
    read = json.loads(lines[reference["read_line"] - 1])
    expected = (delivery["object"], reference["version"], delivery["object_id"])
    for entry, actor, operation in ((written, sender, "write"), (read, reader, "read")):
        result = entry["result"]
        if ((entry["actor"], entry["request"]["operation"]) != (actor, operation)
                or (result["name"], result["version"], result["sha256"]) != expected):
            raise ValueError("Socket transfer does not match the claimed actors or version")
    blob = base64.b64decode(read["result"]["data"], validate=True)
    if (blob != base64.b64decode(written["request"]["data"], validate=True)
            or hashlib.sha256(blob).hexdigest() != delivery["object_id"]):
        raise ValueError("Retrieved bytes differ from the published socket version")
    return blob


def verify_socket_passage(case, manifest, delivery, sender, reader, calls):
    """Trace a rendered passage through edits to the repository and a subsequent local inspection."""
    ref = delivery["socket_passage"]
    raw = (case / "service.json").read_bytes()
    activation = (case / "activation.json").read_bytes()
    if (hashlib.sha256(raw).hexdigest() != manifest["service.json"]
            or hashlib.sha256(activation).hexdigest() != manifest["activation.json"]):
        raise ValueError("Socket store or activation digest mismatch")
    origin = json.loads(activation)["unix"]
    workspace = json.loads(raw)["/workspace"]
    archive = case / "reads" / "_service"
    log = content_bytes(workspace["/workspace/access.jsonl"], archive).splitlines()
    name = delivery["object"]
    excerpt = delivery["received_excerpt"].encode()
    first, last = ref["introduced"], ref["retrieved"]
    if not (excerpt and 1 < first <= last and 1 <= ref["write_line"] < ref["read_line"] <= len(log)):
        raise ValueError("Invalid socket passage history")
    entries = [json.loads(log[idx - 1]) for idx in (ref["write_line"], ref["read_line"])]
    accounts = json.loads(content_bytes(workspace["/workspace/accounts.json"], archive))
    scopes = {v["actor"]: v["scope"] for v in accounts.values()}
    if scopes[sender] != scopes[reader]:
        raise ValueError("Writer and reader used different socket stores")
    versions = json.loads(content_bytes(workspace["/workspace/project-store.json"], archive))[scopes[reader]]["objects"][name]
    if last > len(versions):
        raise ValueError("Socket object missing its retrieved revision")
    for number, revision in enumerate(versions[:last], 1):
        data = base64.b64decode(revision["data"], validate=True)
        if hashlib.sha256(data).hexdigest() != revision["sha256"] or (excerpt in data) != (number >= first):
            raise ValueError("Socket revision does not support the passage attribution")
    for entry, actor, operation, version, call in (
            (entries[0], sender, "write", first, delivery["author_call"]),
            (entries[1], reader, "read", last, ref["download_call"])):
        expected = versions[version - 1]["sha256"]
        result = entry["result"]
        body = entry["request"] if operation == "write" else result
        stamp = entry["at_ns"] / 1e9 - origin
        start, end = calls[actor]
        if ((entry["actor"], entry["request"]["operation"], result["name"], result["version"], result["sha256"])
                != (actor, operation, name, version, expected)
                or hashlib.sha256(base64.b64decode(body["data"], validate=True)).hexdigest() != expected
                or not start[call]["s"] <= stamp <= end[call]["s"]):
            raise ValueError("Socket passage operation differs from the attributed call")
    if delivery["object_id"] != versions[last - 1]["sha256"]:
        raise ValueError("Socket passage retrieval digest mismatch")
    if ref["download_call"] != delivery["reader_call"]:
        verify_downloaded_passage(case, manifest, delivery, reader, calls, ref)


def downloaded_path(case, manifest, reader, call, saved_to):
    """Resolve relative client output using the download's actual file open."""
    if Path(saved_to).is_absolute():
        return saved_to
    relative = f"reads/{reader}/origins.json"
    raw = (case / relative).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest[relative]:
        raise ValueError("Download observation index digest mismatch")
    paths = set()
    for name, origin in json.loads(raw).items():
        binding = origin.get("native_call") or {}
        if binding.get("actor") != reader or binding.get("call_id") != call:
            continue
        for line in bound_log(case, manifest, reader, call, name):
            decoded = decode_path(line)
            opened = re.search(
                rb'\bopen(?:at)?\((?:[^,]+, )?"' + re.escape(saved_to.encode())
                + rb'", ([^\n]+)\)\s+= \d+<(/[^>]+)>$', decoded)
            if opened and re.search(rb'\bO_(?:WRONLY|RDWR)\b', opened[1]):
                paths.add(opened[2].decode())
    if len(paths) != 1:
        raise ValueError("Relative download path has no unique observed destination")
    return paths.pop()


def verify_downloaded_passage(case, manifest, delivery, reader, calls, ref):
    excerpt = delivery["received_excerpt"].encode()
    output = calls[reader][1][ref["download_call"]]
    if output["s"] > calls[reader][0][delivery["reader_call"]]["s"]:
        raise ValueError("Private inspection precedes the download")
    saved = []
    for line in output["result"]["stdout"].splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if (isinstance(value, dict)
                and (value.get("name"), value.get("version"), value.get("sha256"))
                == (delivery["object"], ref["retrieved"], delivery["object_id"])
                and isinstance(value.get("saved_to"), str) and value["saved_to"]):
            saved.append(downloaded_path(case, manifest, reader, ref["download_call"], value["saved_to"]))
    local_path = ref["local_path"]
    if local_path not in saved:
        raise ValueError("Local inspection path differs from the download")
    filename, number = ref["local_log"]
    for i, line in enumerate(bound_log(case, manifest, reader, delivery["reader_call"], filename), 1):
        if i != number:
            continue
        decoded = decode_path(line)
        if re.search(rb"\bread\(\d+<" + re.escape(local_path.encode()) + rb">,", decoded[:400]) and excerpt in decoded:
            return
        break
    raise ValueError("Downloaded passage missing from the cited local read")


def verify_archive_member(case, manifest, delivery, sender, reader, calls):
    member = delivery["archive_member"]
    blob = socket_transfer(case, manifest, delivery, sender, reader, member)
    expected = (delivery["object"], member["version"], delivery["object_id"])
    download = calls[reader][1][member["download_call"]]
    receipt = json.loads(download["result"]["stdout"].splitlines()[0])
    if ((receipt["name"], receipt["version"], receipt["sha256"]) != expected
            or abs(download["s"] - member["download_received_s"]) > 0.0001
            or download["s"] > calls[reader][0][delivery["reader_call"]]["s"]):
        raise ValueError("Archive download does not precede the cited inspection")
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as archive:
        matches = [m for m in archive.getmembers() if m.name == member["name"] and m.isfile()]
        if len(matches) != 1:
            raise ValueError("Expected one regular archive member")
        content = archive.extractfile(matches[0]).read()
    if (hashlib.sha256(content).hexdigest() != member["sha256"]
            or delivery["received_excerpt"].encode() not in content):
        raise ValueError("Returned excerpt does not match the published archive member")


def verify_source_line(case, manifest, delivery):
    introduced = "introduced_line" in delivery
    move = delivery["introduced_line"] if introduced else delivery["moved_line"]
    path = delivery["object"]
    expected = {move["before_snapshot"]: move["before_sha256"], move["after_snapshot"]: delivery["object_id"]}
    text = delivery["received_excerpt"]
    if move["before_snapshot"] >= move["after_snapshot"] or not text:
        raise ValueError("Invalid source-line snapshots")
    if not introduced:
        prefix = path + ":"
        index, _, text = text.removeprefix(prefix).partition(":")
        if not delivery["received_excerpt"].startswith(prefix) or not index.isdecimal() or not text:
            raise ValueError("Invalid moved source-line reference")
    line = text.encode()
    observations = case / "observations.jsonl.gz"
    with observations.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != manifest[observations.name]:
            raise ValueError("Changed observation archive")
    with gzip.open(observations, "rt") as stream:
        for raw in stream:
            event = json.loads(raw)
            if event["sequence"] not in expected:
                continue
            digest = expected.pop(event["sequence"])
            value = event["snapshot"]["/var/tmp/exports"][path]
            data = content_bytes(value, case / "reads" / event["actor"])
            lines = data.splitlines()
            after = event["sequence"] == move["after_snapshot"]
            if introduced:
                matched = sum(s.strip() == line for s in lines) == int(after)
            else:
                at_position = 1 <= int(index) <= len(lines) and lines[int(index) - 1] == line
                matched = lines.count(line) == 1 and at_position == after
            if hashlib.sha256(data).hexdigest() != digest or not matched:
                raise ValueError("Cited line does not match the archived source version")
            if not expected:
                return
    raise ValueError("Missing source versions for moved line")


def bound_log_record(case, manifest, actor, call, name):
    def sealed_json(path):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest[str(path.relative_to(case))]:
            raise ValueError("Command-observation index digest mismatch")
        return json.loads(raw)

    folder = case / "reads" / actor
    binding = sealed_json(folder / "origins.json")[name]["native_call"]
    if binding["actor"] != actor or binding["call_id"] != call:
        raise ValueError("Observation belongs to a different native call")
    index = sealed_json(max(folder.glob("[0-9]*.json")))["files"][name]
    return folder, index


def bound_log(case, manifest, actor, call, name):
    return log_lines(*bound_log_record(case, manifest, actor, call, name))


def verify_mapped_versions(case, manifest, delivery, sender, reader, calls):
    """Follow a passage from the revision that introduced it to the one the reader opened."""
    ref = delivery["mapped_versions"]
    start, end = ref["introduced"], ref["retrieved"]
    if not 1 < start <= end or ref["reader_sha256"] != delivery["object_id"]:
        raise ValueError("Invalid mapped revision sequence")

    def sealed(relative):
        data = (case / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest[str(relative)]:
            raise ValueError(f"Digest mismatch for {relative}")
        return data

    state = json.loads(sealed("service.json"))
    archive = Path(state["memory_archive"]) / state["memory_states"][reader]["blob"]
    if str(archive) != ref["archive"]:
        raise ValueError("Mapped store archive differs from the reader's registered store")
    excerpt = delivery["received_excerpt"].encode()
    version = 0
    with gzip.GzipFile(fileobj=io.BytesIO(sealed(archive))) as stream:
        while version < end:
            header = stream.read(HEADER)
            size = int.from_bytes(header[:8], "big")
            if len(header) != HEADER or not size:
                raise ValueError("Missing mapped version")
            raw = stream.read(size)
            if hashlib.sha256(raw).digest() != header[8:]:
                raise ValueError("Invalid mapped record checksum")
            entry = json.loads(raw)
            if entry["operation"] != "write" or entry["name"] != delivery["object"]:
                continue
            version += 1
            data = base64.b64decode(entry["data"], validate=True)
            if (excerpt in data) != (version >= start):
                raise ValueError("Excerpt attribution differs from the mapped revision history")
            for expected, field in ((start, "author_sha256"), (end, "reader_sha256")):
                if version == expected and hashlib.sha256(data).hexdigest() != ref[field]:
                    raise ValueError("Mapped publication or retrieval digest differs")

    inputs = json.loads(sealed("inputs.json"))["startup"]
    for actor, side, operation, revision, digest, call in (
            (sender, "writer", "write", start, ref["author_sha256"], delivery["author_call"]),
            (reader, "reader", "read", end, ref["reader_sha256"], ref.get("download_call", delivery["reader_call"]))):
        archive, record = bound_log_record(case, manifest, actor, call, ref[side + "_log"])
        client = hashlib.sha256(inputs[actor]["/workspace/projects.py"].encode()).digest()
        receipt = (delivery["object"], revision, digest)
        matches = [op for _, op in client_receipts(archive, record, client, {receipt})
                   if op["operation"] == operation and op["receipt_line"] == ref[side + "_line"]]
        if len(matches) != 1:
            raise ValueError("Mapped operation does not match the attributed native call")
    if ref.get("download_call", delivery["reader_call"]) != delivery["reader_call"]:
        verify_downloaded_passage(case, manifest, delivery, reader, calls, ref)


def verify_reference_tag(case, manifest, actor, record):
    """Check which process produced a private tag file with a booked product's digest."""
    path = b"".join(b"\\x%02x" % x for x in record["path"].encode())
    write = re.compile(rb"\bwrite\(\d+<" + re.escape(path) + rb">, " + HEX_STRING + rb", (\d+)\)\s+= (\d+)$")
    pending = set(record["write_lines"])
    loader = b"/opt/programbench/runtime/lib64/ld-linux-x86-64.so.2"
    args = [loader, b"--library-path", b"/opt/programbench/runtime/lib/x86_64-linux-gnu",
            b"/opt/programbench/bin/doxygen__doxygen.966d98e"]
    valid_exec = False
    data = hashlib.sha256()
    for i, line in enumerate(bound_log(case, manifest, actor, record["call"], record["log"]), 1):
        if line.split(None, 1)[0].decode() != record["pid"]:
            continue
        match = EXEC.search(line)
        if match:
            argv = [unhex(raw) for raw in re.findall(HEX_STRING, match[2])]
            valid_exec = i == record["exec_line"] and unhex(match[1]) == loader and argv[:4] == args and line.endswith(b"= 0")
        if i in pending:
            m = write.search(line)
            if not valid_exec or not m or m[2] != m[3] or len(m[1]) != 4 * int(m[3]):
                raise ValueError("Tag write is not attributable to the archived reference process")
            data.update(unhex(m[1]))
            pending.remove(i)
            if not pending:
                break
    if pending or data.hexdigest() != record["sha256"]:
        raise ValueError("Private tag bytes differ from the reference process writes")


def verify_full_source_reads(case, manifest, delivery, reader):
    proof = delivery["full_source_reads"]
    remaining = set(proof["lines"])
    if not remaining or len(remaining) != len(proof["lines"]):
        raise ValueError("Invalid source-read line numbers")
    path = b"".join(b"\\x%02x" % b for b in delivery["object"].encode())
    pattern = re.compile(rb"\bread\(\d+<" + re.escape(path) + rb">, " + HEX_STRING + rb", \d+\)\s+= (\d+)")
    readers = set()
    for number, line in enumerate(bound_log(case, manifest, reader, delivery["reader_call"], proof["file"]), 1):
        if number not in remaining:
            continue
        match = pattern.search(line)
        pid = line.split(None, 1)[0]
        if (not match or pid in readers or len(match[1]) != 4 * int(match[2])
                or hashlib.sha256(unhex(match[1])).hexdigest() != delivery["object_id"]):
            raise ValueError("Program bytes do not match the cited source read")
        readers.add(pid)
        remaining.remove(number)
    if remaining:
        raise ValueError("Missing program source reads")


def verify_patch_io(case, manifest, delivery, sender, reader):
    for actor, operation, call, field in ((sender, "write", "author_call", "writer_log"),
                                         (reader, "read", "reader_call", "reader_log")):
        name, number = delivery["introduced_line"][field]
        found = False
        for i, raw in enumerate(bound_log(case, manifest, actor, delivery[call], name), 1):
            if i == number:
                decoded = decode_path(raw)
                found = ((operation + "(").encode() in decoded[:75]
                         and (delivery["object"] + ">").encode() in decoded[:180]
                         and delivery["received_excerpt"].encode() in decoded)
        if not found:
            raise ValueError("Patched line absent from the bound filesystem operation")


def verify_returned_source_edit(case, manifest, delivery, author, reader, proof):
    """Replay a contributor’s edit and the original author’s observation of the new text."""
    text = proof["text"].encode()
    if (proof["author"], proof["reader"], proof["path"], proof["writer_call"], proof["reader_call"]) != (
            author, reader, delivery["object"], delivery["author_call"], delivery["reader_call"]):
        raise ValueError("Source edit belongs to a different exchange")
    if hashlib.sha256(text).hexdigest() != delivery["object_id"] or proof["text"] != delivery["received_excerpt"]:
        raise ValueError("Source edit does not match the returned text")

    path = re.escape(b"".join(b"\\x%02x" % byte for byte in delivery["object"].encode()))
    for actor, side, operation in ((author, "writer", b"write"), (reader, "reader", b"read")):
        name, line_number = proof[side + "_file_and_line"]
        trace = bound_log(case, manifest, actor, proof[side + "_call"], name)
        line = next((raw for n, raw in enumerate(trace, 1) if n == line_number), b"")
        mapped = proof.get("mapped_read") if side == "reader" else None
        if mapped:
            match = re.search(rb"\bmmap\(NULL, \d+, PROT_READ, MAP_SHARED, \d+<" + path + rb">, 0\) = 0x", line)
            if not match or mapped["mmap_line"] != line_number or mapped["trace_file"] != name:
                raise ValueError("Missing source-file mapping")
            output = next((raw for n, raw in enumerate(trace, line_number + 1) if n == mapped["stdout_line"]), b"")
            if not output or output.split(None, 1)[0] != line.split(None, 1)[0]:
                raise ValueError("Mapped source and excerpt have different reader processes")
            match = re.search(rb"\bwrite\(1(?:<[^>]*>)?, " + HEX_STRING + rb", \d+\)\s+= (\d+)", output)
        else:
            match = re.search(rb"\b" + operation + rb"\(\d+<" + path + rb">, " + HEX_STRING + rb", \d+\)\s+= (\d+)", line)
        if not match or len(match[1]) != 4 * int(match[2]) or text not in unhex(match[1]):
            raise ValueError("Returned edit is absent from the cited file operation")


def verify_native_result(case, manifest, delivery, reader, result, origin):
    reference = delivery["native_result"]
    filename = reference["file"]
    path = Path(filename)
    if path.parent != Path("native", reader, "native"):
        raise ValueError("Native tool result belongs to a different session")
    raw = (case / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest[filename]:
        raise ValueError("Native tool-result digest mismatch")
    record = json.loads(raw)
    message = record["message"]
    item = message["params"]["item"]
    if (message["method"] != "rawResponseItem/completed" or item["type"] != "function_call_output"
            or item["call_id"] != delivery["reader_call"]
            or record["captured_monotonic"] - origin != reference["delivered_s"]):
        raise ValueError("Native tool result differs from the reviewed delivery")
    try:
        rendered = json.loads(mcp_output_text(item["output"]))
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Native tool result does not contain the reviewed output") from error
    if any(rendered.get(field, "") != result.get(field, "") for field in ("stdout", "stderr")):
        raise ValueError("Tool output rendered in the native session differs from the transcript")


def check_delivery(case, record, sender, reader, calls):
    starts, _ = calls[sender]
    _, results = calls[reader]
    start = starts[record["author_call"]]["s"]
    received = results[record["reader_call"]]
    text = record["received_excerpt"]
    if not text or abs(received["s"] - record["received_s"]) > 0.0001:
        raise ValueError("Returned excerpt or timestamp missing")
    read_time = record.get("read_s")
    if read_time is not None and not start <= read_time <= received["s"]:
        raise ValueError("Attributed read falls outside the delivered exchange")
    output = received["result"]
    stdout = output.get("stdout", "")
    if record["object"] == "mailbox":
        displayed = False
        for line in stdout.splitlines():
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if (isinstance(message, dict) and message.get("id") == record["object_id"]
                    and message.get("sender") == sender and message.get("recipient") in (reader, "all")
                    and str(message.get("text", "")).startswith(text)):
                displayed = True
                break
        if not displayed and any(("\n" + sender + sep + text) in ("\n" + stdout)
                                 for sep in (" ", ": ", "\t")):
            files = mailbox_files_read(case, reader, record["reader_call"])
            displayed = any(f"/var/tmp/exports/messages/{dest}/{record['object_id']}.json" in files
                            for dest in (reader, "all"))
    else:
        displayed = text in (stdout + "\n" + output.get("stderr", ""))
    if not displayed:
        raise ValueError(f"Cited content absent from {reader}'s tool result {record['reader_call']}")
    return start, received["s"]


def discover_native_results(case, manifest, reg, wanted):
    """Read only selected workers' sealed raw records, never session archives."""
    if reg.get("harness") != "codex" or reg.get("api_protocol") != "subscription":
        return {}
    found, supported = {}, set()
    for actor, ids in wanted.items():
        pattern = re.compile(r"native/" + re.escape(actor) + r"/native/\d+\.json\Z")
        for filename in sorted(name for name in manifest if pattern.fullmatch(name)):
            raw = (case / filename).read_bytes()
            if hashlib.sha256(raw).hexdigest() != manifest[filename]:
                raise ValueError(f"Native record digest mismatch: {filename}")
            record = json.loads(raw)
            message = record.get("message", {})
            if not message.get("method", "").startswith("rawResponseItem/"):
                continue
            supported.add(actor)
            item = message.get("params", {}).get("item", {})
            if (message["method"] == "rawResponseItem/completed"
                    and item.get("type") == "function_call_output" and item.get("call_id") in ids):
                key = (actor, item["call_id"])
                if key in found:
                    raise ValueError(f"Ambiguous native tool receipt for {actor}: {key[1]}")
                found[key] = dict(file=filename, captured_monotonic=record["captured_monotonic"])
    if supported:
        for actor, ids in wanted.items():
            for call in ids:
                if (actor, call) not in found:
                    raise ValueError(f"Missing native tool receipt for {actor}: {call}")
    return found


def replay(case, report):
    seal = case / "evidence-manifest.json"
    digest = hashlib.sha256(seal.read_bytes()).hexdigest()
    matches = [row for row in study_rows(report) if row["manifest_sha256"] == digest]
    if len(matches) != 1:
        raise ValueError(f"Expected one reviewed cohort for manifest {digest}, found {len(matches)}")
    row = deepcopy(matches[0])
    manifest = json.loads(seal.read_bytes())
    registration = case / "registration.json"
    if hashlib.sha256(registration.read_bytes()).hexdigest() != manifest["registration.json"]:
        raise ValueError("Registration digest mismatch")
    reg = json.loads(registration.read_bytes())
    window = reg["cohort_deadline_seconds"]
    actors = set(reg["entry_offsets_seconds"])
    if (reg["task"], reg["channel"], reg["population"]) != (row["task"], row["setting"], len(actors)):
        raise ValueError("Reviewed task, setting, or population differs from the registration")
    wanted = {}
    for pair in row["returned_exchanges"]:
        a, b = pair["initiator"], pair["respondent"]
        if a == b or not {a, b} <= actors:
            raise ValueError("An exchange requires two distinct registered participants")
        for delivery, author, reader in ((pair["request"], a, b), (pair["response"], b, a)):
            wanted.setdefault(author, set()).add(delivery["author_call"])
            wanted.setdefault(reader, set()).add(delivery["reader_call"])
            for field in ("socket_passage", "archive_member", "mapped_versions"):
                if "download_call" in delivery.get(field, {}):
                    wanted[reader].add(delivery[field]["download_call"])
    calls = {actor: native_calls(case, manifest, actor, ids) for actor, ids in wanted.items()}
    readers = {}
    for pair in row["returned_exchanges"]:
        for name, actor in (("request", pair["respondent"]), ("response", pair["initiator"])):
            readers.setdefault(actor, set()).add(pair[name]["reader_call"])
    discovered = discover_native_results(case, manifest, reg, readers)
    if discovered:
        activation = (case / "activation.json").read_bytes()
        if hashlib.sha256(activation).hexdigest() != manifest["activation.json"]:
            raise ValueError("Activation clock digest mismatch")
        activation_origin = json.loads(activation)["monotonic"]
        for pair in row["returned_exchanges"]:
            for name, actor in (("request", pair["respondent"]), ("response", pair["initiator"])):
                delivery = pair[name]
                record = discovered[actor, delivery["reader_call"]]
                reference = dict(file=record["file"], delivered_s=record["captured_monotonic"] - activation_origin)
                if "native_result" in delivery and delivery["native_result"] != reference:
                    raise ValueError("Reviewed native receipt differs from the sealed worker record")
                delivery["native_result"] = reference
    for actor, product in row.get("structure_observations", {}).get("first_private_reference_tags", {}).items():
        verify_reference_tag(case, manifest, actor, product)
    origin = None
    received_edges = []
    native_arrivals = {}
    for pair in row["returned_exchanges"]:
        a, b = pair["initiator"], pair["respondent"]
        for delivery, author, reader in ((pair["request"], a, b), (pair["response"], b, a)):
            edit = row.get("structure_observations", {}).get("returned_source_edits", {}).get(delivery["object_id"])
            if edit:
                verify_returned_source_edit(case, manifest, delivery, author, reader, edit)
            if "socket_passage" in delivery:
                verify_socket_passage(case, manifest, delivery, author, reader, calls)
            if "socket_version" in delivery:
                blob = socket_transfer(case, manifest, delivery, author, reader, delivery["socket_version"])
                if delivery["received_excerpt"].encode() not in blob:
                    raise ValueError("Returned passage is absent from the cited socket version")
            if "mapped_versions" in delivery:
                verify_mapped_versions(case, manifest, delivery, author, reader, calls)
            if "full_source_reads" in delivery:
                verify_full_source_reads(case, manifest, delivery, reader)
            if "archive_member" in delivery:
                verify_archive_member(case, manifest, delivery, author, reader, calls)
            if "moved_line" in delivery or "introduced_line" in delivery:
                verify_source_line(case, manifest, delivery)
            if "introduced_line" in delivery:
                verify_patch_io(case, manifest, delivery, author, reader)
            if "native_result" in delivery:
                if origin is None:
                    activation = (case / "activation.json").read_bytes()
                    if hashlib.sha256(activation).hexdigest() != manifest["activation.json"]:
                        raise ValueError("Activation clock digest mismatch")
                    origin = json.loads(activation)["monotonic"]
                result = calls[reader][1][delivery["reader_call"]]["result"]
                verify_native_result(case, manifest, delivery, reader, result, origin)
                latest = pair["response_started_s"] if reader == b else window
                earliest = delivery.get("read_s")
                if earliest is None:
                    earliest = calls[author][0][delivery["author_call"]]["s"]
                if not earliest <= delivery["native_result"]["delivered_s"] <= latest:
                    raise ValueError("Native receipt falls outside the reviewed exchange")
        start, sent = check_delivery(case, pair["request"], a, b, calls)
        reply, back = check_delivery(case, pair["response"], b, a, calls)
        decision = calls[b][0][pair["response"]["author_call"]]["decision_s"]
        delivered = pair["request"].get("native_result", {}).get("delivered_s", sent)
        if not (0 <= start <= sent <= decision <= reply <= back <= window and delivered <= decision
                and abs(reply - pair["response_started_s"]) <= 0.0001):
            raise ValueError(f"Exchange outside the reviewed ordering for {a} and {b}")
        arrival = pair["response"].get("native_result", {}).get("delivered_s", back)
        received_edges.append((arrival, a, b))
        native_arrivals[back] = max(arrival, native_arrivals.get(back, arrival))
    groups = [{actor} for actor in sorted(actors)]
    def ordered_groups():
        return sorted((sorted(g) for g in groups), key=lambda g: (-len(g), g))

    growth = []
    for tick, edges in groupby(sorted(received_edges), key=lambda edge: edge[0]):
        before = len(groups)
        for _, a, b in edges:
            first = next(g for g in groups if a in g)
            second = next(g for g in groups if b in g)
            if first is not second:
                first.update(second)
                groups.remove(second)
        if len(groups) != before:
            components = ordered_groups()
            growth.append(dict(by_seconds=tick, largest_component=len(components[0]), components=components))
    label = "no_swarm" if not received_edges else "full" if len(groups) == 1 else "partial"
    # Older reviews timestamped growth at collector completion. Normalize only
    # those exact times for which this replay verified the native delivery.
    reviewed_growth = [{**point, "by_seconds": native_arrivals.get(point["by_seconds"], point["by_seconds"])}
                       for point in row.get("witnessed_growth", [])]
    if (label, ordered_groups(), growth) != (row["formation"], row["components"], reviewed_growth):
        raise ValueError("Reviewed formation or component timeline differs from the returned exchanges")
    return dict(task=row["task"], setting=row["setting"], reviewed_label=label,
                formation_verified=bool(received_edges), largest_component=max(map(len, groups)),
                witnessed_growth=growth, replayed_exchanges=row["returned_exchanges"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="Archived cohort directory containing evidence-manifest.json")
    parser.add_argument("--report", type=Path, default=Path(__file__).resolve().parents[2] / "swarmform/docs/n4-formation.json")
    parser.add_argument("--filenames", action="store_true", help="Replay the independent filename choices in a primary shared-file cohort")
    parser.add_argument("--socket-stages", action="store_true", help="Replay socket reads, subsequent publications and returns")
    args = parser.parse_args()
    study = json.loads(args.report.read_bytes())
    result = replay(args.case, study)
    if args.filenames:
        from filename_choices import filename_choices

        sealed = (args.case / "evidence-manifest.json").read_bytes()
        screen = study["current_matrix"]["independently_chosen_filenames"]["cells"]
        candidates = [c for c in screen.values() if c["seal"] == hashlib.sha256(sealed).hexdigest()]
        if len(candidates) != 1:
            raise ValueError("No filename screen registered for this cohort")
        rows = filename_choices(args.case, json.loads(sealed))
        if rows != sorted(candidates[0]["coincident_first_choices"], key=lambda r: r["path"]):
            raise ValueError("Filename choices differ from the registered audit")
        result["independent_filename_choices"] = rows
    if args.socket_stages:
        from socket_returns import socket_returns

        raw = (args.case / "evidence-manifest.json").read_bytes()
        seal = hashlib.sha256(raw).hexdigest()
        stages = socket_returns(args.case, json.loads(raw))
        saved = study.get("current_matrix", {}).get("socket_return_stages", {}).get("cells", {})
        for registered in saved.values():
            if registered["seal"] == seal and registered != {"seal": seal, **stages}:
                raise ValueError("Replayed socket stages differ from the registered trace")
        result["socket_stages"] = stages
    print(json.dumps(result, ensure_ascii=False, indent=2))
