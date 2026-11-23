"""Summarize service-side contact evidence from a cohort or an indexed batch ZIP."""
import argparse
import base64
from collections import Counter
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile


def contact(service):
    journal = "/workspace/access.jsonl"
    workspace = service["/workspace"]
    if journal in service.get("file_metadata", {}) and journal not in workspace:
        raise ValueError("Access journal is listed but missing from the snapshot")
    raw = base64.b64decode(workspace.get(journal, ""), validate=True)
    seeds = json.loads(base64.b64decode(workspace.get("/workspace/project-seeds.json", "e30="), validate=True))
    seed_hashes = set(seeds.values())
    owners = {(name, 1, sha): None for name, sha in seeds.items()}
    edges, empty_checks = set(), set()
    has_contribution = False
    counts = Counter()
    events = []
    for line, data in enumerate(raw.splitlines(), 1):
        row = json.loads(data)
        actor, op, result = row["actor"], row["request"]["operation"], row["result"]
        counts[op] += 1
        if op == "list":
            if not result["artifacts"]:
                empty_checks.add(actor)
            continue
        key = result["name"], result["version"], result["sha256"]
        if op == "write":
            owners[key] = actor
            if has_contribution:
                continue
            has_contribution = True
            kind, author = "first_write", actor
        elif op == "read":
            author = owners[key]
            if author is None or author == actor:
                continue
            kind = "peer_read"
            edges.add((author, actor))
        else:
            raise ValueError(f"Unknown operation {op}")
        events.append(dict(kind=kind, line=line, at_ns=row["at_ns"], actor=actor,
                           author=author, name=key[0], version=key[1], sha256=key[2],
                           matches_initial_bytes=key[2] in seed_hashes))
    return dict(operations=dict(counts), empty_list_actors=sorted(empty_checks),
                peer_edges=sorted(edges), reciprocal=any((b,a) in edges for a,b in edges),
                events=events)


def main(source):
    if source.is_dir():
        print(json.dumps(contact(json.loads((source / "service.json").read_bytes()))))
        return
    with ZipFile(source) as archive:
        for index in archive.namelist():
            if PurePosixPath(index).parts[-3:-2] != ("swarmform",) or not index.endswith("/index.json"):
                continue
            for run in json.loads(archive.read(index))["runs"]:
                if run["channel"] != "socket":
                    continue
                folder = PurePosixPath(index).parent.joinpath(*PurePosixPath(run["output"]).parts[-3:])
                name = str(folder / "service.json")
                evidence = (contact(json.loads(archive.read(name))) if name in archive.NameToInfo
                            else {"missing_service_snapshot": True})
                print(json.dumps(dict(cohort=str(folder), task=run["task"], model=run["model"],
                                      status=run["status"], **evidence)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    main(parser.parse_args().source)
