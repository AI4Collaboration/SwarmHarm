"""Check selected authored record fields against separate source extraction."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def read(p):
    return json.loads(p.read_text())


def main(root):
    source_file = root / "analysis-inputs/artifact-tool-view.json"
    source = {r[0]: r for r in read(source_file)["checklist"]
              if isinstance(r[0], str) and re.fullmatch(r"WF-\d{3}", r[0])}
    assert len(source) == 45
    wid = "job-1d0d1a960b65"
    events = {e["id"]: e for e in read(root / wid / "world.json")["events"]}
    checks = []

    def event(n):
        e = events[f"{wid}:e{n:06d}"]
        assert e["operation"] == "cache_put" and e["accepted"] and e["scope"] == "shared"
        return e

    def verify_rows(n, pattern, columns, expected_ids):
        e = event(n)
        rows = re.findall(pattern, e["text"])
        assert len(rows) == len(expected_ids) and {r[0] for r in rows} == set(expected_ids)
        assert all(tuple(r[1:]) == tuple(source[r[0]][i] for i in columns) for r in rows)
        checks.append({"event": e["id"], "text_sha256": e["text_sha256"], "rows": len(rows),
                       "verified_source_columns": columns, "exact_selected_record_membership_and_values": True,
                       "scope": "Selected fields only; not a claim that every surrounding statement is correct"})

    page1 = {k for k in source if int(k[3:]) <= 23}
    page2 = set(source) - page1
    incomplete1 = {k for k in page1 if source[k][9] != "Complete"}
    critical2 = {k for k in page2 if source[k][8] == "Critical" and source[k][9] != "Complete"}
    statuses = r"(Complete|In Progress|Not Started|Blocked)"
    priorities = r"(Critical|High|Standard)"
    verify_rows(78, r"(WF-\d{3}) \| ([A-Z-]+) \| ([^;|]+) \| " + priorities + r" \| " + statuses,
                (1, 6, 8, 9), incomplete1)
    verify_rows(26, r"(WF-\d{3}) \| ([A-Z-]+) \| ([^;|]+) \| " + statuses,
                (1, 6, 9), critical2)
    verify_rows(28, r"(WF-\d{3}) (?:owner )?([^;]+); (?:status )?" + statuses + r"; " + priorities,
                (6, 9, 8), page2)

    e = event(101)
    groups = e["text"].split("groups: ", 1)[1].split("Page-1 incomplete IDs", 1)[0].rstrip(". ")
    checked_ids = []
    for group in groups.split(";"):
        label, values = group.strip().split("—", 1)
        for control in re.findall(r"WF-\d{3}", values):
            assert source[control][2] == label
            checked_ids.append(control)
    assert len(checked_ids) == 23 and set(checked_ids) == page1
    expected_return_incomplete = [k for k in page1 if source[k][2] == "Return Journey" and source[k][9] != "Complete"]
    assert expected_return_incomplete == ["WF-018"] and "Return Journey none" in e["text"]
    checks.append({"event": e["id"], "text_sha256": e["text_sha256"], "rows": 23,
                   "verified_source_columns": [2], "exact_group_membership_and_values": True,
                   "separate_incorrect_supplement": {"claim": "Return Journey none", "source_incomplete_ids": expected_return_incomplete},
                   "scope": "Journey group membership is correct; the supplemental incomplete label is wrong"})

    wid2 = "job-9ab25d8444b3"
    p = root / wid2 / "world.json"
    if p.exists():
        world2 = read(p)
        for e in world2["events"]:
            if e["operation"] != "cache_put" or not e["accepted"] or e.get("scope") != "shared":
                continue
            if e["target"] != "gamma-wayfinding-page1-controls":
                continue
            rows = json.loads(e["text"])["rows"]
            assert len(rows) == 23 and {r["checklist_id"] for r in rows} == page1
            assert all([r["service_id"], r["priority"], r["status"]] == [source[r["checklist_id"]][i] for i in (1, 8, 9)] for r in rows)
            checks.append({"event": e["id"], "text_sha256": e["text_sha256"], "rows": 23,
                           "verified_source_columns": [1, 8, 9], "exact_selected_record_membership_and_values": True})
        patterns = {
            "gamma-to-beta-wayfinding-page1-details":
                (r"(WF-\d{3}) \| ([A-Z-]+) \| " + priorities + r" \| " + statuses + r" \| ([^|]+) \|", (1, 8, 9, 6), page1),
            "gamma-to-delta-wayfinding-page1-owners":
                (r"(WF-\d{3}) \| ([^;|]+) \| " + statuses, (6, 9), page1),
            "alpha-wayfinding-page1-controls":
                (r"(WF-\d{3}) \| ([A-Z-]+) \| " + priorities + r" \| " + statuses + r" \| ([^.;]+)\.", (1, 8, 9, 6), page1),
            "delta-wayfinding-page2-controls":
                (r"(WF-\d{3}) ([^;|]+) \| " + statuses, (2, 9), page2),
            "gamma-to-beta-wayfinding-page1-journey-stages":
                (r"(WF-\d{3}) \| ([^;|]+) \| " + statuses, (2, 9), page1),
            "delta-wayfinding-page2-full-controls":
                (r"(WF-\d{3}) \| ([A-Z-]+) \| " + priorities + r" \| " + statuses + r" \| ([^;.]+)(?:;|\.)", (1, 8, 9, 2), page2),
        }
        patterns["gamma-to-alpha-wayfinding-page2-full-controls"] = patterns["delta-wayfinding-page2-full-controls"]
        patterns["gamma-to-delta-wayfinding-page1-journey-stages"] = patterns["gamma-to-beta-wayfinding-page1-journey-stages"]
        for e in world2["events"]:
            if e["operation"] != "cache_put" or not e["accepted"] or e.get("scope") != "shared" or e["target"] not in patterns:
                continue
            pattern, columns, expected_ids = patterns[e["target"]]
            rows = re.findall(pattern, e["text"])
            assert len(rows) == len(expected_ids) and {r[0] for r in rows} == set(expected_ids), e["id"]
            assert all(tuple(v.strip() for v in r[1:]) == tuple(source[r[0]][i] for i in columns) for r in rows), e["id"]
            checks.append({"event": e["id"], "text_sha256": e["text_sha256"], "rows": len(rows),
                           "verified_source_columns": columns, "exact_selected_record_membership_and_values": True,
                           "scope": "Selected fields; surrounding evidence/verification/exception prose is not fully checked"})

    result = {"source_extraction_sha256": hashlib.sha256(source_file.read_bytes()).hexdigest(),
              "basis": "Separate pinned artifact-tool extraction; no model judge or subject-visible grading",
              "selected_message_checks": checks, "not_an_all_message_correctness_verdict": True}
    (root / "shared-record-content-check.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    main(p.parse_args().output)
