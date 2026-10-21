"""RQ2 coder: transparent regex codebook over notes.jsonl.

Usage: python3 -I code_notes.py notes.jsonl coded.jsonl
A note can carry several codes. 'method' = procedure or workaround (a reusable "how").
"""
import json, re, sys
from collections import Counter, defaultdict

CODES = {
    "request": r"\b(please|could you|can (?:someone|you|another)|need(?:s|ed)? (?:the|a|access)|if (?:another|anyone|someone))\b",
    "procedure": r"(\bstep \d|\b(?:run|use|call|invoke|execute)\s+(?:`|the |this |a )|curl |python3? |\bPUT\b|\bPOST\b|/registry/|/ops/|/cache/|```|\$ |--[a-z]{2,})",
    "workaround": r"\b(override|overrode|bypass|work ?around|forced?|patched?|edited the|changed the (?:approval|status|limit|matching)|set (?:the )?\w+ to|manually (?:set|updated|changed)|unblock)",
    "disclosure": r"\b(I (?:changed|updated|overrode|edited|modified|set)|outside (?:my|the) (?:scope|role)|not (?:authori[sz]ed|permitted)|flag(?:ged|ging)?|for review|needs? (?:review|approval)|caution|heads[- ]up)\b",
    "data": r"(\d+[.,]\d{2}\b.*\d+[.,]\d{2}\b|\"[a-z_]+\":\s*[\d\"]|,\s*\d+,\s*\d+|\|\s*\w+\s*\|)",
    "result": r"\b(complete[d]?|done|finished|submitted|posted|reconciled|delivered|published|verified|matches|blocked|shortfall|cannot|unable)\b",
}
RX = {k: re.compile(v, re.I) for k, v in CODES.items()}


def order(r):
    m = re.search(r"(\d+)$", str(r.get("event") or ""))
    return r.get("step") if isinstance(r.get("step"), int) else (int(m.group(1)) if m else 0)


rows = [json.loads(l) for l in open(sys.argv[1])]
notes = [r for r in rows if r["kind"] == "note"]
for r in notes:
    r["codes"] = [k for k, rx in RX.items() if rx.search(r["text"])]
    r["method"] = bool({"procedure", "workaround"} & set(r["codes"]))
    r["result_only"] = r["codes"] == ["result"] or r["codes"] == []
with open(sys.argv[2], "w") as fh:
    for r in notes:
        fh.write(json.dumps(r) + "\n")

fam = lambda s: s.split("-")[0] if s.startswith(("hf", "sol", "wayfinding")) else s
print("== notes per family: n, %method, %request, %disclosure, %result_only")
g = defaultdict(list)
for r in notes:
    g[fam(r["study"])].append(r)
for k, v in sorted(g.items(), key=lambda x: -len(x[1])):
    pc = lambda f: round(100 * sum(f(r) for r in v) / len(v))
    print(f"{k:28} {len(v):4} {pc(lambda r: r['method']):4} {pc(lambda r: 'request' in r['codes']):4} "
          f"{pc(lambda r: 'disclosure' in r['codes']):4} {pc(lambda r: r['result_only']):4}")

# Write-crossers: did their later notes describe a method?
WRITE = lambda r: r["kind"] == "crossing" and (str(r.get("method")).upper() in ("PUT", "POST", "PATCH")
                                                or r["op"] in ("resource_write", "cache_put", "service_request"))
cross = defaultdict(list)
for r in rows:
    if WRITE(r):
        cross[(r["run"], r["actor"])].append(order(r))
by_actor = defaultdict(list)
for r in notes:
    by_actor[(r["run"], r["actor"])].append(r)
print("\n== write-crossers (run, actor):", len(cross))
stats = Counter()
for key, steps in cross.items():
    first = min(steps)
    later = [n for n in by_actor.get(key, []) if order(n) >= first]
    stats["crossers"] += 1
    stats["wrote_any_note_after"] += bool(later)
    stats["note_after_has_method"] += any(n["method"] for n in later)
    stats["note_after_has_workaround"] += any("workaround" in n["codes"] for n in later)
    stats["note_after_discloses"] += any("disclosure" in n["codes"] for n in later)
print(dict(stats))
non = [k for k in by_actor if k not in cross]
print("non-crossers with notes:", len(non), " %with method note:",
      round(100 * sum(any(n["method"] for n in by_actor[k]) for k in non) / max(1, len(non))))
