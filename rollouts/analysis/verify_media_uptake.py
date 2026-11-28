"""Verify reviewed source-to-master links against an original sealed broadcast cohort."""
import argparse
import base64
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from breakpoints import FD, RENAME, RESULT, decode_path
from channels import events
from run_matrix import sealed_summary
from swarmform import media_batch
from swarmform.read_observer import trace_blocks


def read(path):
    return json.loads(path.read_bytes())


def check(case, record):
    seal = case / "evidence-manifest.json"
    if not sealed_summary(case) or hashlib.sha256(seal.read_bytes()).hexdigest() != record["evidence_manifest_sha256"]:
        raise ValueError("Evidence differs from the reviewed cohort")
    opening = read(case / "inputs.json")["startup"]
    bindings = read(case / "bindings.json")
    jobs = {row["reel"]: row for row in read(case / "truth.json")["jobs"]}
    wanted = {link["staged_observation"] for link in record["uptake"] if "staged_observation" in link}
    terminal, intermediate = {}, {}
    for event in events(case / "observations.jsonl.gz"):
        if event["phase"] == "terminal":
            terminal[event["actor"]] = event
        if event["sequence"] in wanted:
            intermediate[event["sequence"]] = event
    completed = {a: {e["call_id"]: e for e in events(case / f"{a}.jsonl.gz") if e["kind"] == "tool_result"}
                 for a in opening}
    checks = defaultdict(list)
    for link in record["uptake"]:
        owner, reader = link["source_owner"], link["read_by"]
        job = jobs[link["reel"]]
        if [a for a, files in opening.items() if job["path"] in files] != [owner] or owner == reader:
            raise ValueError("Source was not private to its recorded owner")
        shared = link["shared_source_path"]
        actor_state = terminal[reader]
        author_state = terminal[owner]["snapshot"]
        raw = base64.b64decode(author_state["/var/tmp/exports"][shared], validate=True)
        if (raw != opening[owner][job["path"]].encode() or hashlib.sha256(raw).hexdigest() != link["source_sha256"]
                or int(bindings[owner]["user"]) != author_state["file_metadata"][shared]["uid"]):
            raise ValueError("Published source differs from its opening or recorded owner")
        observation = actor_state["snapshot"]
        master = base64.b64decode(observation["/var/tmp/exports"][link["master"]], validate=True)
        if (actor_state["sequence"] != link["terminal_sequence"] or int(bindings[reader]["user"]) != observation["file_metadata"][link["master"]]["uid"]
                or hashlib.sha256(media_batch.y4m(*media_batch.decode(master))).hexdigest() != job["sha256"]
                or link["master_sha256"] != job["sha256"]):
            raise ValueError("Master's owner, frame sequence or observation differs")
        if "staged_master" in link:
            event = intermediate[link["staged_observation"]]
            staged, snapshot = link["staged_master"], event["snapshot"]
            if (event["actor"] != reader or snapshot["file_metadata"][staged]["uid"] != int(bindings[reader]["user"])
                    or base64.b64decode(snapshot["/var/tmp/exports"][staged], validate=True) != master):
                raise ValueError("Staged master differs from the delivered master")
        times = []
        for a, key, timestamp in ((owner, "author_call", "published_s"), (reader, "renderer_call", "render_s"), (reader, "check_call", "verified_s")):
            event = completed[a][link[key]]
            if event["result"]["exit_code"] != 0 or event["s"] != link[timestamp]:
                raise ValueError("Participant call or timestamp differs")
            times.append(event["s"])
        if not times[0] < times[1] <= times[2]:
            raise ValueError("Source-to-use timeline reversed")
        checks[reader, link["source_read"]["strace_log"], link["renderer_call"]].append(link)

    for (reader, log, call), links in checks.items():
        folder = case / "reads" / reader
        binding = read(folder / "origins.json")[log]["native_call"]
        if binding["actor"] != reader or binding["call_id"] != call:
            raise ValueError("Archive log belongs to a different participant command")
        archive = read(sorted(folder.glob("[0-9]*.json"))[-1])["files"][log]
        lines = b"".join(trace_blocks(folder, archive)).splitlines()
        destination_writes = defaultdict(list)
        for number, line in enumerate(lines, 1):
            fd, result = FD.search(line[:1300]), RESULT.search(line[-64:])
            if fd and result and fd[1] in (b"write", b"pwrite64", b"writev") and int(result[1]) > 0:
                destination_writes[decode_path(fd[2])].append(number)
            if b"rename" in line[:120] and (rename := RENAME.search(line)):
                source, target = map(decode_path, rename.groups())
                destination_writes[target] = destination_writes.pop(source, [])
        for link in links:
            proof = link["source_read"]
            line = lines[proof["line"] - 1]
            fd, result = FD.search(line[:1300]), RESULT.search(line[-64:])
            if (not fd or fd[1] not in (b"read", b"pread64", b"readv") or not result or
                    decode_path(fd[2]).decode() != link["shared_source_path"] or
                    int(result[1]) != proof["bytes_read"] or int(result[1]) <= 0):
                raise ValueError("The cited system call did not read the claimed source")
            target = link.get("staged_master", link["master"]).encode()
            if not any(n > proof["line"] for n in destination_writes[target]):
                raise ValueError("The rendering call did not write the claimed master after reading the source")
    return {"cohort": record["case"], "verified_masters": len(record["uptake"]),
            "directed_pairs": sorted({(r["source_owner"], r["read_by"]) for r in record["uptake"]})}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort", type=Path)
    parser.add_argument("--evidence", type=Path, required=True, help="Reviewed cohort JSON with uptake chains")
    args = parser.parse_args()
    print(json.dumps(check(args.cohort, read(args.evidence)), indent=2))
