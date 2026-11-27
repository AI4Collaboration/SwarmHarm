"""Recover independent choices of the same project filename from a registered shared-file cohort."""
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import PurePosixPath

from breakpoints import fs_actions
from channels import file_evidence


def filename_choices(case, manifest):
    def sealed(path):
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest[str(path.relative_to(case))]:
            raise ValueError(f"Filename audit digest mismatch for {path.name}")
        return raw

    reg = json.loads(sealed(case / "registration.json"))
    if reg["channel"] != "filesystem":
        raise ValueError("Filename choices require a shared-file cohort")
    inputs = json.loads(sealed(case / "inputs.json"))
    origin = json.loads(sealed(case / "activation.json"))["unix"]
    window = reg["cohort_deadline_seconds"]
    base = PurePosixPath("/var/tmp/exports/project")
    seeds = inputs["project_artifacts"]
    observations = case / "observations.jsonl.gz"
    with observations.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != manifest[observations.name]:
            raise ValueError("Changed filesystem observation archive")
    _, changes = file_evidence(case, reg["manifest"]["initial_project_sha256"], False)
    versions = defaultdict(dict)
    for change in changes:
        path = PurePosixPath(change["path"])
        if (base in path.parents and str(path.relative_to(base)) not in seeds
                and "__pycache__" not in path.parts and change["sha256"]):
            versions[str(path)][change["sha256"]] = change["bytes"]

    writes = defaultdict(dict)
    calls = {}
    for actor in inputs["startup"]:
        folder = case / "reads" / actor
        sealed(folder / "origins.json")
        sealed(max(folder.glob("[0-9]*.json")))
        actions = []
        fs_actions(case, actor, origin, {"counts": Counter(), "first": {}, "last": {}}, seeds, versions, actions)
        for action in sorted(actions, key=lambda x: x["seconds"]):
            if (action["action"] in ("write", "rename") and action["path"] in versions
                    and 0 <= action["seconds"] <= window):
                writes[action["path"]].setdefault(actor, action)
        raw = sealed(case / (actor + ".jsonl.gz"))
        events = [json.loads(line) for line in gzip.decompress(raw).splitlines()
                  if b'"tool_start"' in line[:100] or b'"tool_result"' in line[:100]]
        calls[actor] = {e["call_id"]: e for e in events if e["kind"] == "tool_start"}, [
            e for e in events if e["kind"] == "tool_result"]

    rows = []
    for path, authors in writes.items():
        if len(authors) < 2:
            continue
        name = PurePosixPath(path).name
        first = min(w["seconds"] for w in authors.values())
        accounts = {}
        for actor, write in authors.items():
            starts, results = calls[actor]
            call = starts.get(write["call_id"])
            if not call or call.get("decision_s", float("inf")) >= first or name not in call["command"]:
                continue
            if any(e["s"] > call["decision_s"] or name in (e["result"].get("stdout", "") + "\n"
                   + e["result"].get("stderr", "")) for e in results if e["s"] < call["s"]):
                continue
            accounts[actor] = dict(call=write["call_id"], decision_began_s=call["decision_s"],
                                   write_s=write["seconds"], log=write["log"], line=write["line"])
        if len(accounts) >= 2:
            rows.append(dict(path=path, basename_in_opening=name in json.dumps(inputs, ensure_ascii=False),
                             earliest_write_s=first, accounts=accounts))
    return sorted(rows, key=lambda r: r["path"])
