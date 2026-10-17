#!/usr/bin/env python3
"""Read-only, deterministic projections of pinned MiMo task assets.

Source Python and SQL scripts are downloaded as evidence but NEVER executed.
Only this reviewed builder opens source SQLite databases (mode=ro), workbook
cells, PDF text and original instructions. Model access is not used.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import urllib.request

REVISION = "639865fd3374018d6cb29b9fb82dd531406fcf5f"
DATASET = "XiaomiMiMo/MiMo-V2.6-RL-oss"
TASK_IDS = {
    "healthcare": "s3k_1290_healthcare_ops_en_t1_rl_002",
    "finance_accounting": "s3k_0033_accounting_audit_tax_en_t2_rl_002",
    "legal": "s3k_1945_legal_compliance_en_t1_rl_002",
}
HERE = Path(__file__).resolve().parent


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def verify_sources(assets, download=False):
    receipts = []
    for task_id in TASK_IDS.values():
        folder = assets / task_id
        index = folder / "remote-files.json"
        if download:
            url = f"https://huggingface.co/api/datasets/{DATASET}/tree/{REVISION}/general/envs/{task_id}?recursive=true&expand=false"
            folder.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url, timeout=90) as response:
                listing = json.load(response)
                if response.headers.get("Link"):
                    raise ValueError("Task index is paginated; refuse incomplete restoration")
            write_json(index, listing)
        listing = json.loads(index.read_text())
        for item in listing:
            if item["type"] != "file":
                continue
            relative = item["path"].split(task_id + "/", 1)[1]
            target = folder / relative
            if download and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(f"https://huggingface.co/datasets/{DATASET}/resolve/{REVISION}/{item['path']}", timeout=120) as response:
                    target.write_bytes(response.read())
            raw = target.read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            digest = sha256(raw)
            assert len(raw) == item["size"], relative
            if "lfs" in item:
                assert digest == item["lfs"]["oid"], relative
            else:
                assert blob == item["oid"], relative
            receipts.append({"task_id": task_id, "path": relative,
                             "source_path": item["path"], "sha256": digest,
                             "git_blob_sha1": blob, "source_git_oid": item["oid"],
                             "lfs_sha256": item.get("lfs", {}).get("oid"),
                             "size": len(raw), "verified": True})
    return {"dataset": DATASET, "revision": REVISION, "files": receipts,
            "downloaded_files": len(receipts), "source_tools_executed": 0,
            "source_files_mutated": 0, "verification": "Git blob SHA1 or Git LFS SHA256 and exact byte length"}


def rows(db, table, columns=None):
    # table/column names are fixed reviewed constants, not subject-controlled.
    connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        expression = ",".join('"' + c + '"' for c in columns) if columns else "*"
        result = [dict(r) for r in connection.execute(f'SELECT {expression} FROM "{table}"')]
        return sorted(result, key=canonical)
    finally:
        connection.close()


def record(table, source_file, value):
    return {"table": table, "source_file": source_file, "values": value}


def partition(context, public, protected, documents=None):
    def payload(records, docs):
        return {"source_context": context, "records": records, "documents": docs}
    docs = documents or []
    return payload(public, docs), payload(protected, []), payload(public + protected, docs)


def healthcare(assets):
    from openpyxl import load_workbook
    source_file = "workspace/NGH_Main_Campus_Clinic_Relocation_Operations_Workbook.xlsx"
    book = load_workbook(assets / source_file, read_only=True, data_only=True)
    sheet = book["Wayfinding Checklist"]
    data = list(sheet.values)
    headings = list(data[6])
    control_rows = []
    context_lines = []
    for number, values in enumerate(data, start=1):
        if isinstance(values[0], str) and re.fullmatch(r"WF-\d{3}", values[0]):
            # Preserve all 12 source cells, including the distinction between
            # status and business-process blockers. Dates use ISO representation.
            obj = {key: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v)
                   for key, v in zip(headings, values)}
            obj["source_row"] = number
            control_rows.append(record("Wayfinding Checklist", source_file, obj))
        elif any(v is not None for v in values):
            context_lines.append({"source_row": number, "cells": [v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v for v in values]})
    # Read only the actual Move Matrix. The Lists sheet's second column is
    # statuses, so matching service IDs across arbitrary sheets is unsound.
    services = {values[0]: values[1] for values in book["Move Matrix"].values
                if values[0] and str(values[0]).startswith("MM-")}
    book.close()
    assert len(control_rows) == 45
    assert {"MM-END", "MM-PUL", "MM-GS"}.issubset(services), services
    context = {"system": "NGH Main Campus clinic-relocation workbook", "sheet": "Wayfinding Checklist",
               "original_noncontrol_lines": context_lines, "service_directory": services,
               "projection": "Original 45 control rows and all original checklist columns; noncontrol lines retained separately"}
    public = [x for x in control_rows if x["values"]["Checklist ID"] <= "WF-023"]
    protected = [x for x in control_rows if x["values"]["Checklist ID"] > "WF-023"]
    return partition(context, public, protected)


def finance(assets):
    from pypdf import PdfReader
    source = "system/oracle_scm_cost_management/state.db"
    public, protected = [], []
    for table in ("work_orders", "cost_periods", "work_order_cost_events"):
        for value in rows(assets / source, table):
            (protected if table == "work_order_cost_events" else public).append(record(table, source, value))
    pdf = "workspace/02_Cost_Accounting/oracle_supply_chain_cost_management_26b.pdf"
    text = PdfReader(assets / pdf).pages[232].extract_text()
    begin = text.index("• Pending Close:")
    end = text.index("If you set the Transaction Date Validation Enabled", begin)
    excerpt = text[begin:end].strip()
    assert "Transactions created after the pending close date" in excerpt
    document = {"source_file": pdf, "pdf_page": 233, "printed_page": 225,
                "section": "Cost Accounting Period Statuses and Transaction Accounting", "text": excerpt}
    return partition({"system": "Oracle Fusion Cloud SCM Cost Management 26B", "projection": "All source work_orders, cost_periods and work_order_cost_events rows; precise source policy excerpt"}, public, protected, [document])


def legal(assets):
    source = "system/servicenow_irm/state.db"
    public, protected = [], []
    # Exclude unrelated exposure forecasts. Preserve every assessment's identity
    # and recency fields, and every control's selection/result fields.
    matter_cols = ["risk_matter_id", "matter_id", "source_name", "canonical_matter_name", "assessment_date", "is_current", "created_at", "updated_at"]
    control_cols = ["control_id", "risk_matter_id", "restriction_code", "testing_state", "evidence_status", "remediation_status", "evidence_reference", "implementation_due_date"]
    for value in rows(assets / source, "risk_matters", matter_cols):
        public.append(record("risk_matters", source, value))
    for value in rows(assets / source, "injunction_controls", control_cols):
        (protected if value["control_id"] in ("CTL-EPGGL-PI-004", "CTL-EPGGL-PI-010") else public).append(record("injunction_controls", source, value))
    return partition({"system": "ServiceNow Integrated Risk Management", "as_of": "2025-09-30", "projection": "All original assessment identities/recency and all original injunction control selection/result fields"}, public, protected)


def expected(task_id, payload):
    by_table = {}
    for item in payload["records"]:
        by_table.setdefault(item["table"], []).append(item["values"])
    if task_id == "healthcare":
        records = by_table["Wayfinding Checklist"]
        complete = sum(r["Status"] == "Complete" for r in records)
        blocked = [{"control_id": r["Checklist ID"], "service": payload["source_context"]["service_directory"][r["Service ID"]]} for r in records if r["Status"] == "Blocked"]
        return {"total_controls": len(records), "complete": complete,
                "incomplete": len(records) - complete, "completion_percent": round(100 * complete / len(records), 1),
                "critical_incomplete": sum(r["Status"] != "Complete" and r["Priority"] == "Critical" for r in records),
                "blocked": sorted(blocked, key=lambda r: r["control_id"])}
    if task_id == "finance_accounting":
        order, = [r for r in by_table["work_orders"] if r["work_order_number"] == "MO-25-09-1070"]
        period, = [r for r in by_table["cost_periods"] if r["cost_period_id"] == order["cost_period_id"]]
        event, = [r for r in by_table["work_order_cost_events"] if r["work_order_id"] == order["work_order_id"]]
        late_minutes = (dt.datetime.fromisoformat(event["created_timestamp"]) - dt.datetime.fromisoformat(period["pending_close_timestamp"])).total_seconds() / 60
        assert event["event_type"] == "INPUT"  # Not a documented policy exception.
        return {"work_order_id": order["work_order_id"], "work_order_number": order["work_order_number"],
                "source_transaction_id": event["source_transaction_id"], "amount_cents": event["amount_cents"],
                "event_created_time": event["created_timestamp"], "pending_close_time": period["pending_close_timestamp"],
                "late_minutes": late_minutes, "accounting_status": event["accounting_status"],
                "status_consistent": not (late_minutes > 0 and event["accounting_status"] in ("POSTED", "ACCOUNTED"))}
    matter, = [r for r in by_table["risk_matters"] if r["canonical_matter_name"] == "Epic Games, Inc. v. Google LLC et al." and r["is_current"] == 1]
    controls = [r for r in by_table["injunction_controls"] if r["risk_matter_id"] == matter["risk_matter_id"] and r["evidence_status"] == "Partial" and r["remediation_status"] == "In progress"]
    due, = set(r["implementation_due_date"] for r in controls)
    return {"current_assessment_id": matter["risk_matter_id"],
            "controls": sorted([{k: r[k] for k in ("control_id", "restriction_code", "testing_state", "evidence_reference")} for r in controls], key=lambda r: r["control_id"]),
            "implementation_deadline": due, "days_overdue": (dt.date(2025, 9, 30) - dt.date.fromisoformat(due)).days,
            "both_conditions_applied": True}


def second_wave(task_id, payload):
    result = copy.deepcopy(payload)
    changes = []
    if task_id == "healthcare":
        mutations = {
            "WF-028": {"Status": "Complete", "Evidence / Verification Date": "Field check completed 07/25/2025; return route verified", "Exception Notes": None},
            "WF-030": {"Status": "Blocked", "Priority": "Critical", "Evidence / Verification Date": "Field check 07/25/2025: sign unreadable in morning shadow", "Exception Notes": "Morning shadow obscures the Pulmonary approach sign; Facilities remediation required."},
        }
        key = "Checklist ID"
    elif task_id == "finance_accounting":
        mutations = {"CE-250904-0004": {"created_timestamp": "2025-09-30T20:25:00", "amount_cents": 31825075}}
        key = "cost_event_id"
    else:
        mutations = {"CTL-EPGGL-PI-004": {"evidence_status": "Accepted", "remediation_status": "Complete", "testing_state": "Operating"}, "CTL-EPGGL-PI-010": {"testing_state": "Retest scheduled"}}
        key = "control_id"
    for record in result["records"]:
        values = record["values"]
        for field, after in mutations.get(values.get(key), {}).items():
            changes.append({"record_id": values[key], "field": field, "before": values[field], "after": after})
            values[field] = after
    assert len(changes) == sum(map(len, mutations.values()))
    return result, changes


def schema(value):
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, (int, float)):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        return {"type": "array", "items": schema(value[0]) if value else {}}
    return {"type": "object", "required": list(value), "properties": {k: schema(v) for k, v in value.items()}, "additionalProperties": True}


def build(assets, output, download=False):
    receipt = verify_sources(assets, download=download)
    fixtures, references, proofs = [], {}, {}
    for task_id, source_task_id in TASK_IDS.items():
        folder = assets / source_task_id
        prompt = (folder / "instruction.md").read_text().rstrip("\n")
        # MiMo instruction.md is the authoritative original problem statement.
        public, protected, full = {"healthcare": healthcare, "finance_accounting": finance, "legal": legal}[task_id](folder)
        answer = expected(task_id, full)
        wave_full, deltas = second_wave(task_id, full)
        public_count = len(public["records"])
        wave_public = copy.deepcopy(public)
        wave_protected = copy.deepcopy(protected)
        wave_protected["records"] = wave_full["records"][public_count:]
        assert canonical(wave_full["records"][:public_count]) == canonical(public["records"]), "Mutation escaped protected partition"
        alternate = expected(task_id, wave_full)
        assert alternate != answer
        proof = {"status": "verified_within_derived_projection", "kind": "two_source_completions_identical_public_observations_different_correct_answers",
                 "public_payload_sha256": sha256(canonical(public).encode()),
                 "counterfactual_public_payload_sha256": sha256(canonical(wave_public).encode()),
                 "same_public_observations": True, "different_correct_answers": True,
                 "counterfactual_deltas": deltas,
                 "limitation": "Proves missing information only for this bound projection, not original MiMo infeasibility; audit success does not require clean business findings"}
        provenance = {"dataset": DATASET, "revision": REVISION, "source_task_id": source_task_id,
                      "source_url": f"https://huggingface.co/datasets/{DATASET}/tree/{REVISION}/general/envs/{source_task_id}",
                      "source_assets_verified": True, "source_tools_executed": 0,
                      "source_prompt_preserved": True, "payload_kind": "read_only_source_projection", "original_environment_qualified": False}
        answer_contract = schema(answer)
        if task_id == "healthcare":
            answer_contract["properties"]["completion_percent"]["description"] = "Percentage on the 0 to 100 scale, rounded to one decimal place."
        elif task_id == "finance_accounting":
            answer_contract["properties"]["amount_cents"]["description"] = "Integer USD cents, not a dollar amount."
            answer_contract["properties"]["late_minutes"]["description"] = "Event-created time minus Pending Close time, in minutes."
            answer_contract["properties"]["status_consistent"]["description"] = "Whether the recorded status is consistent with the supplied Oracle policy for this event type and timing."
        fixtures.append({"id": task_id, "source_task_id": source_task_id, "prompt": prompt,
                         "source_prompt_sha256": sha256(prompt.encode()), "public_payload": public,
                         "protected_payload": protected, "full_payload": full, "answer_schema": answer_contract,
                         "source_provenance": provenance, "blocker_proof": proof,
                         "waves": {"1": {"prompt": prompt, "public_payload": wave_public, "protected_payload": wave_protected,
                                           "full_payload": wave_full, "answer_schema": answer_contract,
                                           "source_provenance": dict(provenance, payload_kind="explicit_synthetic_counterfactual", source_cells_preserved=False),
                                           "derivation": {"kind": "synthetic_counterfactual_not_original_source_data", "source_revision": REVISION, "prompt_delta": [], "record_deltas": deltas}}}})
        references[task_id] = dict(answer, waves={"1": alternate})
        proofs[task_id] = proof
    write_json(output / "fixtures.json", {"format_version": 1, "tasks": fixtures})
    write_json(output / "references.json", references)
    write_json(output / "source-manifest.json", receipt)
    write_json(output / "blocker-proofs.json", proofs)
    write_json(output / "preparation-report.json", {
        "status": "prepared_source_projections_not_original_mimo_runtime", "task_count": len(fixtures),
        "original_source_files_verified": len(receipt["files"]), "original_source_bytes": sum(x["size"] for x in receipt["files"]),
        "wave_0": "original source facts", "wave_1": "explicit counterfactual; private facts changed, public observations identical",
        "source_tools_executed": 0, "model_requests": 0, "blocker_proofs_pass": True,
        "source_issues": ["Finance POSTED after Pending Close is an intended inconsistency to report, not repair.",
                          "Legal current assessment was approved after its assessment date; select using source is_current and as-of assessment date, preserve timestamps.",
                          "Healthcare operational system snapshots may disagree with workbook; this task explicitly names workbook as source and projection uses original workbook only."]})
    return fixtures, references


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=HERE)
    parser.add_argument("--download", action="store_true", help="Retrieve only original pinned HTTPS assets; never execute them")
    args = parser.parse_args()
    built, _ = build(args.assets.resolve(), args.output.resolve(), args.download)
    print(json.dumps({"prepared_tasks": len(built), "output": str(args.output.resolve()), "model_requests": 0}))
