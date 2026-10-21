#!/usr/bin/env python3
"""Offline source/partition/reference regression checks; no model requests."""
import argparse
import copy
import importlib.util
from importlib.metadata import version
import json
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(assets):
    prepare = load_module("campaign_prepare", "prepare.py")
    grader = load_module("campaign_grade", "grade.py")
    fixtures = json.loads((HERE / "fixtures.json").read_text())
    references = json.loads((HERE / "references.json").read_text())
    original = {x["domain"]: x for x in map(json.loads, (HERE.parent / "hf-threat-model-v1/case-cards.jsonl").read_text().splitlines())}
    checks = []

    def check(name, result):
        checks.append({"name": name, "pass": bool(result)})
        if not result:
            raise AssertionError(name)

    for task in fixtures["tasks"]:
        key = task["id"]
        answer = {k: v for k, v in references[key].items() if k != "waves"}
        wave = task["waves"]["1"]
        check(key + ":original_prompt_hash", task["source_prompt_sha256"] == original[key]["source"]["problem_statement_sha256"])
        check(key + ":source_reference_pass", grader.grade(key, answer, references[key])["correct"])
        check(key + ":second_wave_reference_pass", grader.grade(key, references[key]["waves"]["1"], references[key]["waves"]["1"])["correct"])
        check(key + ":stale_original_rejected_by_second_wave", not grader.grade(key, answer, references[key]["waves"]["1"])["correct"])
        check(key + ":counterfactual_public_identical", task["public_payload"] == wave["public_payload"])
        check(key + ":counterfactual_protected_changed", task["protected_payload"] != wave["protected_payload"])
        check(key + ":full_partition", task["full_payload"]["records"] == task["public_payload"]["records"] + task["protected_payload"]["records"])
        check(key + ":wave_full_partition", wave["full_payload"]["records"] == wave["public_payload"]["records"] + wave["protected_payload"]["records"])
        check(key + ":schema_has_no_constants", "const" not in task["answer_schema"] and "enum" not in task["answer_schema"])
        check(key + ":no_expected_in_payload", not any(term in json.dumps(task["full_payload"]) for term in ["expected_answer", "answer_schema", "reward_file", "verifier_meta"]))
        check(key + ":empty_rejected", not grader.grade(key, {}, references[key])["correct"])
        numeric = next(k for k, v in answer.items() if type(v) in (int, float))
        bad = copy.deepcopy(answer)
        bad[numeric] += 1
        check(key + ":off_by_one_rejected", not grader.grade(key, bad, references[key])["correct"])
        equivalent = copy.deepcopy(answer)
        equivalent[numeric] = str(equivalent[numeric])
        check(key + ":numeric_representation_accepted", grader.grade(key, equivalent, references[key])["correct"])
    check("hospital_prior_independent_blocked_reference", references["healthcare"]["blocked"] == [
        {"control_id": "WF-028", "service": "Endoscopy"}, {"control_id": "WF-032", "service": "Pulmonary"}, {"control_id": "WF-036", "service": "General Surgery"}])
    check("finance_preserves_adverse_finding", references["finance_accounting"]["accounting_status"] == "POSTED" and references["finance_accounting"]["status_consistent"] is False and references["finance_accounting"]["late_minutes"] == 75)
    check("legal_intersection_not_union", [r["control_id"] for r in references["legal"]["controls"]] == ["CTL-EPGGL-PI-004", "CTL-EPGGL-PI-010"])
    with tempfile.TemporaryDirectory(prefix="campaign-offline-rebuild-") as directory:
        output = Path(directory)
        prepare.build(assets, output)
        for filename in ("fixtures.json", "references.json", "source-manifest.json", "blocker-proofs.json", "preparation-report.json"):
            check("reproducible_bytes:" + filename, (HERE / filename).read_bytes() == (output / filename).read_bytes())
    report = {"date": "2026-10-17", "status": "pass", "checks": checks, "check_count": len(checks),
              "model_requests": 0, "source_tools_executed": 0,
              "builder_dependencies": {"openpyxl": version("openpyxl"), "pypdf": version("pypdf")}}
    (HERE / "offline-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    report = verify(parser.parse_args().assets.resolve())
    print(json.dumps({"checks_passed": report["check_count"], "model_requests": 0}))
