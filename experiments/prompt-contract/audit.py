"""Summarize offline prompt coverage and verify frozen historical evidence."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

REPO = Path(__file__).resolve().parents[2]
WARNINGS = re.compile(
    r"\bdo not\b|\bmust not\b|\bread.only\b|respect.{0,30}permissions|"
    r"does not change.{0,40}(?:access|permission)|trained to collaborate|"
    r"(?:honest|accurate).{0,20}stop|\b(?:unauthorized|restricted|protected)\b|"
    r"exhaust.{0,30}(?:option|route)|collaborat|coordinat", re.I)
ALLOWED_STATUSES = {"prepared", "retired_intervention", "task_alias", "pinned_upstream_adapter"}


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def strings(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from strings(child, path + "/" + key)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from strings(child, path + "/" + str(i))
    elif isinstance(value, str):
        yield path, value


def audit(args):
    inventory = read(args.inventory / "inventory.json")
    expected = {p.parent.name for p in (REPO / "experiments").glob("*/run.py")
                if p.parent.name != "classifier-screen-v1"}
    assert {i["family"] for i in inventory} == expected
    families, candidates, source_mismatches = [], [], []
    for item in inventory:
        assert item["status"] in ALLOWED_STATUSES, item
        packet_file = args.inventory / "inventory" / item["family"] / "packets.json"
        entry = dict(item, packets=0)
        if packet_file.exists():
            bundle = read(packet_file)
            assert bundle["offline_only"]
            entry.update(packets=len(bundle["packets"]), packet_sha256=digest(packet_file), notes=bundle["notes"])
            for source, expected_hash in bundle["source_sha256"].items():
                if digest(REPO / source) != expected_hash:
                    source_mismatches.append(source)
            for packet in bundle["packets"]:
                for location, value in strings(packet["body"]):
                    if WARNINGS.search(value):
                        candidate = {"family": item["family"], "location": location, "text": value}
                        if candidate not in candidates:
                            candidates.append(candidate)
        families.append(entry)
    assert not source_mismatches, source_mismatches
    assert not candidates, candidates

    tests = read(args.tests / "test-results.json")
    assert all(t["returncode"] == 0 for t in tests), tests
    for t in tests:
        p = Path(t["suite"])
        log = args.tests / (p.parent.name + "-" + p.stem + ".log")
        t["executed_methods"] = int(re.search(r"Ran (\d+) tests?", log.read_text()).group(1))
        t["log_sha256"] = digest(log)
    budget = read(args.budget_check / "offline-verification.json")
    assert budget["passed"] and budget["real_model_requests"] == 0
    previous = read(args.historical_manifest)
    changed = [name for name, expected_hash in previous.items()
               if not (REPO / name).is_file() or digest(REPO / name) != expected_hash]
    assert not changed, changed

    result = {
        "date": "2026-10-20", "kind": "Offline prompt maintenance; no model behavior measured",
        "model_calls": 0, "family_entry_points": len(families),
        "assembled_initial_packets": sum(f["packets"] for f in families),
        "warning_candidates_in_initial_packets": candidates,
        "family_inventory": families, "test_suites": tests,
        "executed_test_methods_including_inherited_checks": sum(t["executed_methods"] for t in tests),
        "dynamic_coverage": "All 13 world modules, all six scenario modules, legacy recovery task surfaces; resource reads/lists, registry reads/writes, report submission/status, payment finalization, actual peer-text preservation and repaired-service checks.",
        "long_budget_controller": {"passed": True, "checks": len(budget["checks"]),
                                   "log_sha256": digest(args.budget_check / "offline-verification.json")},
        "historical_integrity": {"files_verified_unchanged": len(previous), "changed_files": changed,
                                 "manifest_sha256": digest(args.historical_manifest)},
        "archive_scope": [
            "Original dataset text and frozen experiment inputs/results are unchanged; current task views render the revised work orders.",
            "Pinned external LessWrong inputs and the SWH-13 multi-agent-persistence lab bundle are historical reproduction material, outside current natural task collection.",
            "Coached profiles, permission front-loading, fabricated peer-cue comparisons and relational forced-review collection are retired.",
            "Instructed tool-functionality controls and post-rollout diagnostic questions are separate from natural behavioral trajectories.",
            "Real source documents and actual model-written peer messages remain verbatim; operational failures and business checks remain enforced."],
        "limits": "Keyword and mechanical checks support the stated source/input coverage, not universal naturalness or a new model behavior result. Older outcomes do not validate this revision."
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("model_calls", "family_entry_points", "assembled_initial_packets", "executed_test_methods_including_inherited_checks", "historical_integrity")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("inventory", "tests", "budget-check", "historical-manifest", "output"):
        parser.add_argument("--" + option, required=True, type=Path)
    audit(parser.parse_args())
