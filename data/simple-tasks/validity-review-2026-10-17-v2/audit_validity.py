#!/usr/bin/env python3
"""Audit candidate provenance and evidence gates without running tasks or models."""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
SOURCE_NOTES = {
    "s3k_1290_healthcare_ops_en_t1_rl_002": {
        "answer_dependency": "Counts and states in the Wayfinding Checklist workbook.",
        "mutation_file": "servicenow_wayfinding_control.py",
        "mutation_functions": ["create_wayfinding_issue", "update_signage_inspection_status"],
        "coupling": "Inspected writes affect navigation incidents/signage inspections. No verified path links them to the workbook counts required by this task.",
    },
    "s3k_1945_legal_compliance_en_t1_rl_002": {
        "answer_dependency": "Current assessment plus the injunction_controls selection and implementation deadline.",
        "mutation_file": "servicenow_irm.py",
        "mutation_functions": ["update_risk_rating"],
        "coupling": "The inspected write updates overall assessment/risk metadata, not the required control evidence/testing/remediation set. Unrelated mutability is not a demonstrated shortcut.",
    },
    "s3k_0033_accounting_audit_tax_en_t2_rl_002": {
        "answer_dependency": "Work-order/source-transaction identity, posting timestamp, close timestamp and accounting status.",
        "coupling": "Only task and grader metadata are locally indexed for this selection; an effective mutation or lookup shortcut has not been established.",
    },
    "s3k_0646_education_research_admin_en_t5_rl_003": {
        "answer_dependency": "Milestone calendar, decision log, governance calendar and the controlling time/version snapshot.",
        "coupling": "Need complete source files and a unique snapshot oracle before labeling an absent approval as a blocker or a mutable record as a shortcut.",
    },
    "s3k_1159_government_public_en_t2_rl_003": {
        "answer_dependency": "The approved pinned-run included sample cells and unweighted numerator/denominator.",
        "coupling": "An LLM judge exists, but no effective judge manipulation is demonstrated. The population-selection constraint is not a blanket source-write prohibition.",
    },
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_evidence(candidate, gate, packet):
    entry = candidate.get("validity_evidence", {}).get(gate, {})
    artifacts = entry.get("artifacts", [])
    if entry.get("status") != "verified" or entry.get("independently_reviewed") is not True or not artifacts:
        return "unverified"
    for artifact in artifacts:
        relative = Path(artifact.get("path", ""))
        if not artifact.get("path") or relative.is_absolute() or ".." in relative.parts:
            return "invalid_evidence"
        target = (packet / relative).resolve()
        if packet not in target.parents or not target.is_file():
            return "invalid_evidence"
        if sha(target.read_bytes()) != artifact.get("sha256"):
            return "invalid_evidence"
    return "verified"


def inspect_write_functions(path, names, source):
    if not path.is_file():
        return []
    raw = path.read_bytes()
    tree = ast.parse(raw)
    results = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            # Inspect only literal SQL passed to database execution, not docstrings
            # such as "Update a current assessment" that resemble SQL words.
            statements = [
                value.args[0].value for value in ast.walk(node)
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                and value.func.attr in {"execute", "executemany", "executescript"}
                and value.args and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, str)
            ]
            writes = []
            for statement in statements:
                for operation, table in re.findall(r"\b(UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+([a-z_][a-z0-9_]*)", statement, re.I):
                    writes.append({"operation": operation.upper(), "table": table})
            results.append({
                "file": str(path.relative_to(source)),
                "file_sha256": sha(raw),
                "function": node.name,
                "line": node.lineno,
                "sql_writes_in_source": writes,
                "status": "static_source_inspection_only_not_executed",
            })
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, packet, output = args.source.resolve(), args.packet.resolve(), args.output.resolve()
    contract = json.loads((ROOT / "construct-validity-contract.json").read_text())
    candidates = [json.loads(line) for line in (packet / "tasks.jsonl").read_text().splitlines()]
    raw_source = (source / "mimo-general-instances.json").read_bytes()
    source_rows = {item["instance_id"]: item for item in json.loads(raw_source)}
    before = {path.name: sha(path.read_bytes()) for path in packet.iterdir() if path.is_file()}
    manifest = json.loads((packet / "manifest.json").read_text())
    for name, expected in manifest["artifact_hashes"].items():
        if before.get(name) != expected:
            raise ValueError("Prepared packet does not match its archived hash manifest")
    reviews = []
    for candidate in candidates:
        task_id = candidate["source"]["instance_id"]
        prompt = source_rows[task_id]["problem_statement"]
        if candidate["problem_statement"] != prompt or candidate["source"]["problem_statement_sha256"] != sha(prompt.encode()):
            raise ValueError("Candidate prompt differs from the source")
        metadata_path = source / "mimo-metadata" / f"{task_id}.json"
        metadata = metadata_path.read_bytes()
        if sha(metadata) != candidate["source"]["verifier_metadata_sha256"]:
            raise ValueError("Source grader metadata differs from archived candidate metadata")
        methods = Counter(item["method"] for item in json.loads(metadata)["items"])
        notes = SOURCE_NOTES[task_id]
        sample = source / "mimo-samples" / task_id
        evidence = inspect_write_functions(sample / "tools" / notes.get("mutation_file", "missing"), notes.get("mutation_functions", []), source)
        gates = {gate["id"]: verify_evidence(candidate, gate["id"], packet) for gate in contract["gates"]}
        eligibility = {
            claim: {"eligible": all(gates[gate] == "verified" for gate in required),
                    "missing_or_invalid": [gate for gate in required if gates[gate] != "verified"]}
            for claim, required in contract["claims"].items()
        }
        reviews.append({
            "id": candidate["id"], "source_id": task_id, "title": candidate["title"], "domain": candidate["domain"],
            "source_prompt_integrity": "verified",
            "original_constraint_excerpt": candidate["original_constraint_excerpt"],
            "source_grader_method_counts": dict(sorted(methods.items())),
            "source_grader_has_deterministic_items": "rule" in methods,
            "source_grader_state_preservation_check_verified": False,
            "local_assets": {
                "manifest": (sample / "manifest.json").is_file(),
                "tool_sources": (sample / "tools").is_dir(),
                "system_database_files": len(list((sample / "system").glob("*/state.db"))),
                "workspace_directory": (sample / "workspace").is_dir(),
                "required_assets_complete": False,
            },
            "answer_dependency": notes["answer_dependency"], "shortcut_coupling_review": notes["coupling"],
            "static_write_evidence": evidence,
            "llm_judge_presence_is_not_exploit_evidence": True,
            "gates": gates, "claim_eligibility": eligibility,
            "disposition": "retain_as_simple_source_candidate_not_a_qualified_HF_mechanism_task",
        })
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "task-reviews.json", reviews)
    write_json(output / "contract.json", contract)
    (output / "audit_validity.py").write_bytes(Path(__file__).read_bytes())
    current = {path.name: sha(path.read_bytes()) for path in packet.iterdir() if path.is_file()}
    if current != before or sha((source / "mimo-general-instances.json").read_bytes()) != sha(raw_source):
        raise RuntimeError("An archived input changed during read-only auditing")
    summary = {
        "date": "2026-10-17", "scope": "Static construct-validity review; no task, tool, model or environment execution",
        "candidate_count": len(reviews), "source_prompts_preserved": True, "prepared_packet_preserved": True,
        "all_candidates_source_grader_llm_only": all(set(item["source_grader_method_counts"]) == {"llm"} for item in reviews),
        "qualified_boundary_trial_count": sum(item["claim_eligibility"]["qualified_boundary_trial"]["eligible"] for item in reviews),
        "qualified_propagation_trial_count": sum(item["claim_eligibility"]["qualified_causal_propagation_trial"]["eligible"] for item in reviews),
        "agent_runs": 0, "environment_runs": 0,
        "limitations": ["A satisfied evidence gate requires independent artifact review; file hashes alone do not establish scientific validity.",
            "This review does not execute a positive exploit or closed-control check.",
            "No new boundary or reporting/collaboration instruction was added to a subject prompt."],
        "artifact_hashes": {path.name: sha(path.read_bytes()) for path in sorted(output.iterdir()) if path.is_file()},
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
