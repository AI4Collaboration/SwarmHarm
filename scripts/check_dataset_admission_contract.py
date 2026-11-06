#!/usr/bin/env python3
"""Validate the continuous-input contract and separately preserved evidence."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/dataset-admission-contract.json"
STATUS = ROOT / "docs/live-rollout-status.json"
REGISTRATIONS = ROOT / "experiments/swarmharm-v1/registrations"
ROLLOUT_LANGUAGE_PATHS = [
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "experiments/swarmharm-v1/README.md",
    ROOT / "experiments/swarmharm-v1/format-contract.json",
    ROOT / "experiments/swarmharm-v1/protocol.json",
    ROOT / "experiments/swarmharm-v1/domain-scenarios.json",
]


def fail(message):
    raise SystemExit("contract check failed: " + message)


def validate_rollout_language():
    paths = ROLLOUT_LANGUAGE_PATHS + sorted((ROOT / "docs").rglob("*.md"))
    paths += sorted((ROOT / "docs").rglob("*.json"))
    for source_root in (
        ROOT / "experiments/swarmharm-v1",
        ROOT / "experiments/prompt-contract",
    ):
        for suffix in ("*.py", "*.json", "*.md"):
            paths += [
                path for path in source_root.rglob(suffix)
                if "registrations" not in path.parts
            ]
    retired_execution_term = "campa" + "ign"
    retired_business_term = "pro" + "gram"
    retired_business_pattern = re.compile(
        rf"\b{retired_business_term}\b|{retired_business_term}_|_{retired_business_term}\b",
        re.IGNORECASE,
    )
    for path in sorted(set(paths)):
        content = path.read_text()
        if retired_execution_term in path.name.lower() or retired_execution_term in content.lower():
            fail(f"non-rollout terminology remains in {path.relative_to(ROOT)}")
        if retired_business_pattern.search(path.name) or retired_business_pattern.search(content):
            fail(f"non-scenario terminology remains in {path.relative_to(ROOT)}")


def validate_readiness(contract, status):
    readiness_path = ROOT / status.get("readiness_reference", "")
    if not readiness_path.is_file():
        fail("current readiness index is missing")
    readiness = json.loads(readiness_path.read_text())
    claims = readiness.get("claims", {})
    required = {"coordinated_adverse_outcomes", "compositional_failure", "shared_false_inference"}
    if set(claims) != required or set(status.get("claim_cases", {})) != required:
        fail("current claim coverage differs from the three maintained claims")
    if contract["current_evidence"]["phase2_readiness"] != str(readiness_path.relative_to(ROOT)):
        fail("status and admission point to different readiness snapshots")
    audit_path = ROOT / contract["current_evidence"]["trajectory_completeness"]
    audit = json.loads(audit_path.read_text())
    if audit_path != readiness_path.parent / readiness["extension_review"]:
        fail("current interface review is not the current completeness audit")
    verified = {a["url"]: a for a in audit.get("verified_baseline_archives", [])}
    positive_fields = {
        "coordinated_adverse_outcomes": "passed",
        "compositional_failure": "composition",
        "shared_false_inference": "shared_false_authorization_prerequisite",
    }

    def assets_in(value):
        if isinstance(value, dict):
            if "url" in value and "sha256" in value:
                yield value
            for child in value.values():
                yield from assets_in(child)
        elif isinstance(value, list):
            for child in value:
                yield from assets_in(child)

    for claim, entry in claims.items():
        if not entry.get("ready") or status["claim_cases"][claim] != entry.get("case"):
            fail(f"stale readiness or case selection for {claim}")
        path = readiness_path.parent / entry["review"]
        if contract["current_evidence"].get(claim) != str(path.relative_to(ROOT)):
            fail(f"admission evidence differs from readiness for {claim}")
        review = json.loads(path.read_text())
        observations = {r["case"]: r for r in review.get("rollouts", review.get("observations", []))}
        selected = entry.get("selected_positive_cases", [])
        if not selected or len(selected) != len(set(selected)):
            fail(f"missing or duplicated selected cases for {claim}")
        for case in selected:
            if observations.get(case, {}).get(positive_fields[claim]) is not True:
                fail(f"selected case does not support {claim}: {case}")
            archives = [a for a in assets_in(review)
                        if a["url"].endswith("/" + case + "-complete-trajectory.tar.gz")]
            if not archives:
                fail(f"complete trajectory asset is missing for {case}")
            for asset in archives:
                checked = verified.get(asset["url"], {})
                if (not checked.get("remote_digest_verified")
                        or checked.get("sha256") != asset["sha256"]
                        or checked.get("size") != asset["size"]):
                    fail(f"complete trajectory audit differs for {case}")
        if sorted({observations[c]["model"] for c in selected}) != entry.get("positive_models"):
            fail(f"positive-model summary differs for {claim}")

    # The reviewed extension is a frozen snapshot, separate from current source.
    # Its negative results must not become an implementation pass flag.
    reviewed = readiness.get("reviewed_extension", {})
    expected = {(preset, model) for preset in ("grader", "trace", "information")
                for model in ("openai/gpt-5.6-sol", "openai/gpt-6.1-sol")}
    rows = audit.get("rollouts", [])
    if len(rows) != len(expected) or {(r["preset"], r["model"]) for r in rows} != expected:
        fail("current interface checks do not cover the registered paired model set")
    if (audit["revision"] != reviewed.get("source_revision")
            or audit["source_commit"] != reviewed.get("behavior_commit")
            or audit["registration_commit"] != reviewed.get("collection_commit")
            or not audit["setup"]["matched_task_tool_and_initial_file_audits"]):
        fail("reviewed extension source or matched-input audit differs")
    for row in rows:
        asset = row["trajectory_archive"]
        if (row.get("native_atif_actors") != 4 or not row.get("native_atif_valid")
                or not row.get("original_scores_preserved")
                or not row["outcome"].get("full_action_results_match")
                or not row["outcome"].get("final_files_match")
                or not asset.get("remote_digest_verified")
                or not asset["url"].endswith("/" + row["case"] + "-complete-trajectory.tar.gz")
                or any(len(row.get(key, "")) != 64 for key in
                       ("registration_sha256", "evidence_manifest_sha256", "post_review_manifest_sha256"))):
            fail("incomplete current interface evidence: " + row["case"])


def validate_phase1_results(contract):
    path = ROOT / contract['current_evidence']['phase1_current_results']
    results = json.loads(path.read_text())
    cases = results.get('cases', [])
    ids = [entry['rollout'] for entry in cases]
    if len(ids) != 8 or len(set(ids)) != len(ids) or any(not name.startswith('phase1-') for name in ids):
        fail('Phase 1 evidence needs distinct full run identifiers')
    expected = {(domain, setting) for domain in ('Engineering', 'Data Analysis',
                'Financial Analysis', 'Knowledge Work')
                for setting in ('information_dependent', 'impossible')}
    if {(row['domain'], row['task_setting']) for row in cases} != expected:
        fail('Native formation evidence does not cover four domains and two settings')
    if not results.get('original_results_preserved') or not results.get('download_verification'):
        fail('Formation archives need preserved scores and download verification')
    for entry in cases:
        if (not entry.get('formation_passed') or len(entry.get('source_commit', '')) != 40
                or not re.fullmatch('[0-9a-f]{64}', entry.get('archive_sha256', ''))
                or entry.get('native_tool_returns', 0) <= 0 or entry.get('full_raw_files', 0) <= 0):
            fail('Incomplete native formation archive: ' + entry['rollout'])
        if not entry.get('download', '').endswith('/' + entry['rollout'] + '.tar.gz'):
            fail('Formation archive identifier mismatch: ' + entry['rollout'])


def main():
    validate_rollout_language()
    contract = json.loads(CONTRACT.read_text())
    status = json.loads(STATUS.read_text())

    if contract.get("active_scope") != "continuous-unified":
        fail("current development scope must be continuous unified input")
    if status.get("active_scope") != "continuous-unified" or status.get('study_mode') != 'unified':
        fail("live status differs from the continuous input")

    architecture = contract.get("architecture", {})
    for field in ('one_task', 'persistent_session_and_world', 'all_business_tools_from_start'):
        if architecture.get(field) is not True:
            fail('Continuous input invariant missing: ' + field)
    for field in ('phase_transition', 'formation_gate', 'announced_peers', 'supplied_peer_messages'):
        if architecture.get(field) is not False:
            fail('Continuous input must not enable ' + field)
    if architecture.get("fresh_connected_registration_supported"):
        fail("fresh connected registration must remain disabled")

    phase1 = contract.get("communication", {})
    if phase1.get("agents") != 4 or not phase1.get('live_exact_read_dialogue_required'):
        fail("Communication evidence must preserve four actors and exact dialogue")
    if phase1.get("full_pairwise_reciprocal_closure_required"):
        fail("Communication incorrectly requires full pairwise reciprocal closure")
    if phase1.get("full_pairwise_reciprocal_closure_reported") is not True:
        fail("Retain pairwise reciprocal closure as an optional diagnostic")

    phase2 = contract.get("outcomes", {})
    if phase2.get("minimum_distinct_causal_contributors") != 2:
        fail("Phase 2 contributor minimum differs")
    if not phase2.get("independent_terminal_outcome_required"):
        fail("Phase 2 terminal outcome is not independently verified")
    if phase2.get("reply_roundtrip_required"):
        fail("Phase 2 incorrectly requires another reply round trip")
    if not phase2.get("supplied_method_must_be_labeled"):
        fail("supplied method provenance is not required")

    for relative in contract.get("current_evidence", {}).values():
        if not (ROOT / relative).is_file():
            fail(f"missing current evidence {relative}")

    if status.get("heartbeat") is not None:
        fail("unexpected scheduled collection")
    for entry in status.get("active_rollouts", []):
        if not isinstance(entry, dict) or not isinstance(entry.get("registration"), str):
            fail("active_rollouts entries must name a repository-relative registration")
        if entry["registration"] not in status.get("maintained_registrations", []):
            fail("active rollout registration is not maintained")
    expected = set(status.get("maintained_registrations", []))
    actual = {
        str(path.relative_to(ROOT)) for path in REGISTRATIONS.iterdir()
        if path.is_dir() and (path / "registration.json").is_file()
    }
    if actual != expected:
        fail(f"maintained registrations differ: {sorted(actual ^ expected)}")
    if not (ROOT / status["decision_record"]).is_file():
        fail("current decision record is missing")

    validate_readiness(contract, status)
    validate_phase1_results(contract)
    print("dataset admission contract: valid; continuous input and original case evidence aligned")


if __name__ == "__main__":
    main()
