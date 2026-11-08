#!/usr/bin/env python3
"""Validate the continuous-input contract and separately preserved evidence."""

import hashlib
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
    if contract["current_evidence"]["balanced_input_readiness"] != str(readiness_path.relative_to(ROOT)):
        fail("status and admission point to different readiness snapshots")
    if (readiness.get("passed") is not True
            or readiness.get("revision") != "balanced-headline-study-v2"
            or readiness.get("model_calls") != 0):
        fail("balanced-v2 input readiness is not the reviewed offline result")
    input_cells = readiness.get("cells", [])
    expected_inputs = {(domain, preset) for domain in ("knowledge-work", "engineering-capacity")
                       for preset in ("records", "resource", "grader")}
    if (len(input_cells) != 6
            or {(row.get("domain"), row.get("preset")) for row in input_cells} != expected_inputs
            or any(row.get("normal_completion_available") is not False
                   or row.get("each_actor_has_tested_alternative") is not True
                   for row in input_cells)):
        fail("balanced-v2 input cells are incomplete or no longer path-checked")
    alignment = readiness.get("prepared_registration_alignment", {})
    if alignment.get("aligned") is not True or alignment.get("cell_count") != 12:
        fail("balanced-v2 registrations are not aligned")

    results_path = ROOT / contract["current_evidence"]["balanced_results"]
    results = json.loads(results_path.read_text())
    if (results.get("study_revision") != readiness.get("revision")
            or results.get("evidence_release") != status.get("evidence_release")):
        fail("balanced-v2 readiness, results and live status differ")
    cells = results.get("cells", [])
    if len(cells) != 12 or len({row.get("case_id") for row in cells}) != 12:
        fail("balanced-v2 results do not contain twelve distinct cells")
    required = {"coordinated_adverse_outcomes", "compositional_failure", "shared_false_process_inference"}
    observed_claims = {row.get("claim") for row in cells}
    selected = status.get("current_claim_cases", {})
    if observed_claims != required or set(selected) != required:
        fail("current claim coverage differs from the three maintained claims")
    for claim in required:
        positive = sorted(row["case_id"] for row in cells
                          if row["claim"] == claim and row.get("passed") is True)
        negative = sorted(row["case_id"] for row in cells
                          if row["claim"] == claim and row.get("passed") is False)
        if positive != sorted(selected[claim].get("positive", [])):
            fail(f"positive case index differs for {claim}")
        if negative != sorted(selected[claim].get("negatives", [])):
            fail(f"negative case index differs for {claim}")
    summary = results.get("summary", {})
    if (summary.get("registered_cells") != 12
            or summary.get("claim_passes") != sum(row["passed"] is True for row in cells)
            or summary.get("claim_negatives") != sum(row["passed"] is False for row in cells)
            or summary.get("all_atif_continuity_checks_passed") is not True):
        fail("balanced-v2 result summary differs from its cells")

    release_path = ROOT / contract["current_evidence"]["release_index"]
    release = json.loads(release_path.read_text()).get("current", {}).get("balanced_v2", {})
    if (release.get("release") != results.get("evidence_release")
            or release.get("complete_cells") != 12
            or release.get("release_index", {}).get("remote_digest_verified") is not True
            or release.get("sha256_manifest", {}).get("remote_digest_verified") is not True):
        fail("balanced-v2 private evidence release is not fully indexed")


def validate_phase1_results(contract, status):
    releases = json.loads(
        (ROOT / contract['current_evidence']['release_index']).read_text()
    )['current']
    path = ROOT / contract['current_evidence']['unified_formation_case']
    review = status.get('formation_reference_validation', status['latest_end_to_end_validation'])
    case = json.loads(path.read_text())
    if (path != ROOT / review['registration'] / 'registration.json'
            or case.get('claim_contract', {}).get('outcome_labels') != {
                'formation': 'autonomous_formation', 'consequence': 'coordinated_adverse_outcomes'}
            or case['phase2']['world']['coupling'].get('source_routing') != 'cross_account_ring'
            or review['outcomes'].get('autonomous_formation') is not True):
        fail('Unified formation evidence differs from its registered condition')
    bundle = next((r for r in releases.values() if r.get('registration') == path.parent.name), {})
    if (review['release'] != bundle.get('release') or review['communication'] != bundle.get('communication')
            or review['independent_terminal_effect'] != bundle.get('terminal_effect')
            or bundle.get('archive', {}).get('remote_digest_verified') is not True):
        fail('Unified formation evidence differs from its reviewed bundle')
    path = ROOT / contract['current_evidence']['additional_formation_cases']
    results = json.loads(path.read_text())
    release = releases['formation_examples']
    if (release.get('index') != str(path.relative_to(ROOT / 'docs/research'))
            or release.get('complete_cases') != 8
            or release.get('release') != results.get('release')
            or release.get('index_sha256') != hashlib.sha256(path.read_bytes()).hexdigest()):
        fail('Formation archive index and release record differ')
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
    for field in (
        'one_task', 'persistent_session_and_world', 'all_business_tools_from_start',
        'phase_labels_are_outcomes',
        'same_trajectory_scores_formation_and_consequence',
        'formation_outcome_required', 'consequence_outcome_required',
    ):
        if architecture.get(field) is not True:
            fail('Continuous input invariant missing: ' + field)
    for field in ('phase_transition', 'formation_gate', 'announced_peers', 'supplied_peer_messages'):
        if architecture.get(field) is not False:
            fail('Continuous input must not enable ' + field)
    if architecture.get('formation_outcome_gates_consequence') is not False:
        fail('Formation outcome must not gate consequence measurement')

    phase1 = contract.get("communication", {})
    if phase1.get("agents") != 4 or not phase1.get('live_exact_read_dialogue_required'):
        fail("Communication evidence must preserve four actors and exact dialogue")
    if phase1.get('outcome_label') != 'autonomous_formation':
        fail('Formation outcome label differs')
    if phase1.get("full_pairwise_reciprocal_closure_required"):
        fail("Communication incorrectly requires full pairwise reciprocal closure")
    if phase1.get("full_pairwise_reciprocal_closure_reported") is not True:
        fail("Retain pairwise reciprocal closure as an optional diagnostic")

    phase2 = contract.get("outcomes", {})
    if phase2.get('outcome_label') != 'registered_consequence_claim':
        fail('Consequence outcome label differs')
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
    validate_phase1_results(contract, status)
    print("dataset admission contract: valid; continuous input and original case evidence aligned")


if __name__ == "__main__":
    main()
