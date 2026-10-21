"""Read-before-write funnel over crossings in notes.jsonl.

Usage: python3 -I funnel.py notes.jsonl out.csv [notes.jsonl.actors.jsonl]
Per (run, actor) with any crossing: first crossing read, first crossing write (row order follows
event order inside each run). A write is PUT/POST/PATCH or a write-type operation.
With the actors file it also compares, per family, how often actors who crossed on a read
later crossed on a write against actors who never crossed on a read.
"""
import csv, json, sys
from collections import Counter, OrderedDict

WRITE_OPS = ("resource_write", "cache_put", "service_request", "project_write")


def is_write(r):
    return str(r.get("method")).upper() in ("PUT", "POST", "PATCH") or r["op"] in WRITE_OPS


def family(study):
    return study.split("-")[0] if study.startswith(("hf", "sol", "wayfinding")) else study


actors = OrderedDict()
for i, line in enumerate(open(sys.argv[1])):
    r = json.loads(line)
    if r["kind"] != "crossing":
        continue
    a = actors.setdefault((r["run"], r["actor"]), dict(family=family(r["study"]), model=r["model"], run=r["run"], actor=r["actor"],
                                                     reads=0, writes=0, first_read=None, first_write=None))
    k = "write" if is_write(r) else "read"
    a[k + "s"] += 1
    if a["first_" + k] is None:
        a["first_" + k] = i

for a in actors.values():
    if a["writes"] and a["reads"]:
        a["pattern"] = "read_then_write" if a["first_read"] < a["first_write"] else "write_then_read"
    else:
        a["pattern"] = "write_only" if a["writes"] else "read_only"

with open(sys.argv[2], "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["family", "model", "run", "actor", "reads", "writes", "pattern"], extrasaction="ignore")
    w.writeheader()
    w.writerows(actors.values())
print(len(actors), "actors with a crossing")
for fam in sorted({a["family"] for a in actors.values()}):
    print(fam, dict(Counter(a["pattern"] for a in actors.values() if a["family"] == fam)))
print("all", dict(Counter(a["pattern"] for a in actors.values())))

if len(sys.argv) > 3:
    everyone = {}
    for line in open(sys.argv[3]):
        r = json.loads(line)
        if r["actor"]:
            everyone[(r["run"], r["actor"])] = family(r["study"])
    print("== write crossing after a read crossing vs no read crossing")
    for fam in ("hf", "sol", "wayfinding"):
        keys = [k for k, f in everyone.items() if f == fam]
        readers = [k for k in keys if k in actors and actors[k]["reads"]]
        others = [k for k in keys if k not in readers]
        later = sum(actors[k]["pattern"] == "read_then_write" for k in readers)
        alone = sum(k in actors and actors[k]["writes"] > 0 for k in others)
        print(f"{fam}: {later}/{len(readers)} read-crossers later wrote across; {alone}/{len(others)} others did")
        # Same comparison inside runs where somebody did cross on a write, so both groups had the chance.
        open_runs = {k[0] for k in keys if k in actors and actors[k]["writes"]}
        r2 = [k for k in readers if k[0] in open_runs]
        o2 = [k for k in others if k[0] in open_runs]
        if open_runs:
            print(f"  in {len(open_runs)} runs with a write crossing: {sum(actors[k]['pattern'] == 'read_then_write' for k in r2)}/{len(r2)}"
                  f" vs {sum(k in actors and actors[k]['writes'] > 0 for k in o2)}/{len(o2)}")
