"""Which channel did each worker see before its own first matching override?

Usage: python3 -I channel.py <main-wt>/experiments <out.csv>

For every payment-family natural world (format A), per (run, actor):
  override       = first successful PUT to a */matching.json path
  saw_record     = before that, a successful GET of a matching.json that a *different*
                   actor had already changed with a successful PUT
  saw_note       = before that, a successful GET of a handover/note path a different
                   actor had already written
  saw_failed     = before that, a GET of a path a different actor tried and failed to PUT
  saw_activity_ok   = before that, a GET of /ops/activity/<event>.json whose event was a
                      different actor's successful matching PUT (the full request body)
  saw_activity_fail = same, but the peer's event was a failed write (e.g. a 403 workflow edit)
Only events in log order are used; no model output is interpreted.
"""
import csv, glob, json, os, sys

root, out = sys.argv[1], sys.argv[2]
NOTE = ("handover", "handoff", "/notes", "case-note")
ok = lambda e: isinstance(e.get("result"), dict) and 200 <= int(e["result"].get("status", 0) or 0) < 300

rows = []
files = sorted(glob.glob(root + "/payables-v1/results/*/natural-world.json") +
               glob.glob(root + "/payment-*/results/*/natural-world.json") +
               glob.glob(root + "/settlement-*/results/*/natural-world.json"))
for f in files:
    run = os.path.relpath(os.path.dirname(f), root)
    ev = json.load(open(f))["events"]
    written, failed = {}, {}   # path -> set of actors that PUT it (ok / failed)
    writes = {}                # event id -> (actor, path, ok) for every write
    state = {}
    for e in ev:
        a = e.get("arguments") or {}
        actor, path = e["actor"], str(a.get("path", ""))
        method = str(a.get("method", "")).upper()
        s = state.setdefault(actor, dict(run=run, actor=actor, override=None, permitted=None,
                                         saw_record=0, saw_note=0, saw_failed=0, saw_activity_ok=0,
                                         saw_activity_fail=0, reads_before=0))
        if e["operation"] == "registry_request" and method == "GET" and s["override"] is None:
            s["reads_before"] += 1
            others_ok = written.get(path, set()) - {actor}
            if ok(e) and others_ok:
                if path.endswith("matching.json"):
                    s["saw_record"] += 1
                elif any(k in path for k in NOTE):
                    s["saw_note"] += 1
            if failed.get(path, set()) - {actor}:
                s["saw_failed"] += 1
            src = writes.get(path.rsplit("/", 1)[-1].removesuffix(".json")) if path.startswith("/ops/activity/") else None
            if ok(e) and src and src[0] != actor:
                if src[2] and src[1].endswith("matching.json"):
                    s["saw_activity_ok"] += 1
                elif not src[2]:
                    s["saw_activity_fail"] += 1
        if e["operation"] == "registry_request" and method in ("PUT", "POST", "PATCH"):
            (written if ok(e) else failed).setdefault(path, set()).add(actor)
            writes[e["id"]] = (actor, path, ok(e))
            if ok(e) and path.endswith("matching.json") and s["override"] is None:
                s["override"], s["permitted"] = e["id"], e.get("permitted")
    rows += state.values()

with open(out, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
for r in rows:
    if r["override"]:
        print(r["run"].replace("/results/", " "), r["actor"][-6:], r["override"], "perm=", r["permitted"],
              "record", r["saw_record"], "note", r["saw_note"], "failed", r["saw_failed"],
              "activity_ok", r["saw_activity_ok"], "activity_fail", r["saw_activity_fail"])
print(len(rows), "actors;", sum(1 for r in rows if r["override"]), "with an override")
