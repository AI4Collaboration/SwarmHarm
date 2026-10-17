#!/usr/bin/env python3
"""Derive an operator reference from an unchanged workbook using two parsers."""
import argparse
from collections import Counter
from datetime import date, datetime
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import openpyxl

ROOT = Path(__file__).resolve().parent
BOOK = "NGH_Main_Campus_Clinic_Relocation_Operations_Workbook.xlsx"
SHEET = "Wayfinding Checklist"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def serial(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def xml_sheets(path):
    """Read OOXML directly, independently of openpyxl's object model."""
    with ZipFile(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ["".join(item.itertext()) for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        relations = {item.attrib["Id"]: item.attrib["Target"] for item in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        result = {}
        for item in ET.fromstring(archive.read("xl/workbook.xml")).findall("s:sheets/s:sheet", NS):
            target = relations[item.attrib[f"{{{REL}}}id"]]
            member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            cells = {}
            for cell in ET.fromstring(archive.read(member)).findall("s:sheetData/s:row/s:c", NS):
                text, formula = cell.find("s:v", NS), cell.find("s:f", NS)
                kind = cell.attrib.get("t")
                if formula is not None:
                    value = "=" + (formula.text or "")
                elif kind == "inlineStr":
                    value = "".join(node.text or "" for node in cell.findall(".//s:t", NS))
                elif text is None:
                    value = None
                elif kind == "s":
                    value = shared[int(text.text)]
                else:
                    value = text.text
                cells[cell.attrib["r"]] = value
            result[item.attrib["name"]] = cells
        return result


def summarize(rows, services):
    statuses = Counter(row[9] for _, row in rows)
    if not rows or set(statuses) - {"Complete", "In Progress", "Not Started", "Blocked"}:
        raise ValueError("Unexpected control status")
    blocked = [{"control_id": row[0], "service_id": row[1], "service": services[row[1]]}
               for _, row in rows if row[9] == "Blocked"]
    completed = statuses["Complete"]
    return {
        "total_controls": len(rows), "complete": completed,
        "incomplete": len(rows) - completed,
        "completion_fraction": str(Fraction(completed, len(rows))),
        "completion_percent": round(100 * completed / len(rows), 1),
        "critical_incomplete": sum(row[8] == "Critical" and row[9] != "Complete" for _, row in rows),
        "blocked": sorted(blocked, key=lambda item: item["control_id"]),
        "status_counts": dict(sorted(statuses.items())),
    }


def primary_reference(grid, services):
    controls = [(number, row) for number, row in enumerate(grid, 1)
                if isinstance(row[0], str) and re.fullmatch(r"WF-\d{3}", row[0])]
    ids = [row[0] for _, row in controls]
    if len(set(ids)) != len(ids) or any(not row[1] or not row[8] or not row[9] for _, row in controls):
        raise ValueError("Incomplete/duplicate control record")
    return controls, summarize(controls, services)


def independent_reference(cells, matrix):
    """Use a table-record predicate and a separate aggregation, not the ID regex."""
    header_rows = [int(key[1:]) for key, value in cells.items() if key.startswith("A") and value == "Checklist ID"]
    if len(header_rows) != 1:
        raise ValueError("Missing/ambiguous table header")
    header = header_rows[0]
    max_row = max(int(re.search(r"\d+$", key)[0]) for key in cells)
    selected = [number for number in range(header + 1, max_row + 1)
                if cells.get(f"B{number}") and cells.get(f"I{number}") in {"Critical", "High", "Standard"}
                and cells.get(f"J{number}") in {"Complete", "In Progress", "Not Started", "Blocked"}]
    service_map = {value: matrix.get(f"B{key[1:]}") for key, value in matrix.items()
                   if key.startswith("A") and isinstance(value, str) and value.startswith("MM-")}
    completed = sum(cells[f"J{number}"] == "Complete" for number in selected)
    histogram = {}
    blocked = []
    critical = 0
    for number in selected:
        status = cells[f"J{number}"]
        histogram[status] = histogram.get(status, 0) + 1
        if status != "Complete" and cells[f"I{number}"] == "Critical":
            critical += 1
        if status == "Blocked":
            service_id = cells[f"B{number}"]
            blocked.append({"control_id": cells[f"A{number}"], "service_id": service_id, "service": service_map[service_id]})
    return selected, {
        "total_controls": len(selected), "complete": completed, "incomplete": len(selected) - completed,
        "completion_fraction": str(Fraction(completed, len(selected))),
        "completion_percent": float(round(100 * Fraction(completed, len(selected)), 1)),
        "critical_incomplete": critical, "blocked": sorted(blocked, key=lambda item: item["control_id"]),
        "status_counts": dict(sorted(histogram.items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--artifact-view", type=Path, required=True, help="Read-only artifact-tool cell extraction")
    parser.add_argument("--output", type=Path, required=True, help="A new operator-only reference directory")
    args = parser.parse_args()
    receipt_bytes = (args.sources / "source-receipt.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    spec = json.loads((ROOT / "source-files.json").read_text())
    if receipt["revision"] != spec["revision"] or receipt["source_spec_sha256"] != sha((ROOT / "source-files.json").read_bytes()):
        raise ValueError("Source receipt does not match the pinned spec")
    from fetch_sources import verify
    source_hashes = {}
    for entry in spec["files"]:
        raw = (args.sources / entry["name"]).read_bytes()
        verify(raw, entry)
        source_hashes[entry["name"]] = sha(raw)
    book = args.sources / BOOK
    workbook = openpyxl.load_workbook(book, read_only=True, data_only=False)
    grid = [[serial(value) for value in row] for row in workbook[SHEET].values]
    matrix = [[serial(value) for value in row[:2]] for row in workbook["Move Matrix"].values]
    if grid[6] != ["Checklist ID", "Service ID", "Journey Stage", "Asset Type", "Location / Channel", "Required Wording / Check", "Owner", "Due Date", "Priority", "Status", "Evidence / Verification Date", "Exception Notes"]:
        raise ValueError("Unexpected schema")
    service_map = {row[0]: row[1] for row in matrix if isinstance(row[0], str) and row[0].startswith("MM-")}
    controls, answer = primary_reference(grid, service_map)
    direct = xml_sheets(book)
    independent_rows, independent_answer = independent_reference(direct[SHEET], direct["Move Matrix"])
    if [number for number, _ in controls] != independent_rows or answer != independent_answer:
        raise ValueError("Independent reference disagreement")
    artifact_bytes = args.artifact_view.read_bytes()
    artifact = json.loads(artifact_bytes)
    if len(artifact["checklist"]) != len(grid) or artifact["services"] != matrix:
        raise ValueError("Artifact-tool shape/service mapping disagreement")
    for number, row in enumerate(grid, 1):
        for column in (0, 1, 8, 9):
            if artifact["checklist"][number - 1][column] != row[column]:
                raise ValueError("Artifact-tool core cell disagreement")
    for number, row in controls:
        for column in ("A", "B", "I", "J"):
            index = ord(column) - ord("A")
            if direct[SHEET].get(f"{column}{number}") != row[index]:
                raise ValueError("OOXML core cell disagreement")
    records = [json.loads(line) for line in (args.packet / "tasks.jsonl").read_text().splitlines()]
    task = next(item for item in records if item["source"]["instance_id"] == spec["instance_id"])
    prompt = task["problem_statement"].encode()
    if sha(prompt) != task["source"]["problem_statement_sha256"]:
        raise ValueError("Original prompt hash mismatch")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    dump(output / "worksheet-view.json", {
        "kind": "derived_input_projection_not_a_replacement_source_workbook",
        "source_workbook": BOOK, "source_sha256": source_hashes[BOOK],
        "sheets": {SHEET: grid, "Move Matrix": matrix},
        "projection": {SHEET: "A1:L54", "Move Matrix": "A1:B13"},
    })
    dump(output / "answer.json", answer)
    dump(output / "independent-answer.json", independent_answer)
    dump(output / "row-classification.json", {
        "control_rows": independent_rows,
        "excluded_rows": [number for number in range(1, len(grid) + 1) if number not in independent_rows],
        "primary_rule": "Unique WF-NNN ID plus populated service, priority and status; exact original column schema.",
        "independent_rule": "Rows after table header with populated Service ID and valid priority/status, without the control-ID regex.",
        "cached_summary_used_as_gold": False,
        "source_grader_used_as_gold": False,
        "source_ranges": ["Wayfinding Checklist!A1:L54", "Move Matrix!A1:B13"],
    })
    (output / "original-task.txt").write_bytes(prompt)
    dump(output / "provenance.json", {
        "family_id": "swarmharm/wayfinding-local-v1", "source_task_id": task["id"],
        "source_revision": spec["revision"], "source_hashes": source_hashes,
        "source_receipt_sha256": sha(receipt_bytes), "artifact_tool_view_sha256": sha(artifact_bytes),
        "artifact_tool_core_cells_agree": True,
        "reference_methods": [f"openpyxl {openpyxl.__version__}, control ID enumeration", "stdlib ZIP/XML, table-record enumeration"],
        "independent_reference_agrees": True,
        "prompt_sha256": sha(prompt), "builder_sha256": sha(Path(__file__).read_bytes()),
        "model_requests": 0, "source_tools_executed": 0,
        "source_files_unchanged": all(sha((args.sources / name).read_bytes()) == expected for name, expected in source_hashes.items()),
        "original_mimo_environment_qualified": False,
    })
    workbook.close()
    dump(output / "manifest.json", {path.name: sha(path.read_bytes()) for path in sorted(output.iterdir()) if path.is_file()})
    print(json.dumps({"status": "operator_reference_verified", "answer": answer, "source_files": len(source_hashes), "model_requests": 0}))


if __name__ == "__main__":
    main()
