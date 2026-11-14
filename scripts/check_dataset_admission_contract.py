#!/usr/bin/env python3
"""Validate retained SwarmHarm reporting inputs and their preserved evidence."""

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/dataset-admission-contract.json"
ACTIVE_STATUS = ROOT / "swarmform/docs/live-rollout-status.json"
REPORTING = ROOT / "swarmharm/docs/research/reporting-run-index.json"
RETAINED_CASES = ROOT / "swarmharm/docs/research/retained-positive-cases.json"
REGISTRATIONS = ROOT / "swarmharm/registrations"
REGISTRATION_ROOTS = (REGISTRATIONS, ROOT / "swarmform/registrations")


def fail(message):
    raise SystemExit("contract check failed: " + message)


def retained_case_registrations():
    """Validate original seals for the retained positive examples."""
    ledger = json.loads(RETAINED_CASES.read_text())
    entries = [row['registration_directory'] for row in ledger['cases']]
    retained = set()
    for entry in entries:
        if isinstance(entry, dict):
            entry = entry['registration_directory']
        folder = (ROOT / 'swarmharm' / entry).resolve()
        if folder.parent != REGISTRATIONS.resolve():
            fail(f"retained case registration is outside the maintained directory: {entry}")
        registration = folder / 'registration.json'
        seal = folder / 'registration-seal.json'
        if not registration.is_file() or not seal.is_file():
            fail(f"retained case registration lacks sealed inputs: {entry}")
        if json.loads(seal.read_text()).get('sha256') != hashlib.sha256(registration.read_bytes()).hexdigest():
            fail(f"retained case registration seal differs: {entry}")
        retained.add(str(folder.relative_to(ROOT)))
    return retained


def mechanism_registrations():
    """Bind current inputs to their exact positive case and preserved seal."""
    ledger = json.loads((ROOT/'swarmharm/docs/research/mechanism-input-status.json').read_text())
    configurations = {name for model in ledger['taxonomy'].values()
                      for name in model['configurations']}
    expected_inputs = {f'{domain}/{name}' for domain in ledger['domain_workloads']
                       for name in configurations}
    admitted_inputs = {row['id'] for row in ledger['inputs']}
    gaps = {row['id'] for row in ledger['coverage_gaps']}
    if (len(expected_inputs) != ledger['planned_inputs']
            or len(admitted_inputs) != len(ledger['inputs'])
            or not admitted_inputs <= expected_inputs
            or gaps != expected_inputs - admitted_inputs
            or any(row['current_input_validation'] != 'reviewed_positive'
                   for row in ledger['inputs'])):
        fail('default input coverage differs from the admitted positive cases')
    if ledger['delivery_ready'] is not (admitted_inputs == expected_inputs):
        fail('delivery readiness requires a matching positive for every default input')
    workloads = [*ledger['inputs'], *ledger.get('workload_inputs', [])]
    entries = {row['registration'] for row in workloads if row.get('registration')}
    entries.update(ledger.get('retained_registrations', []))
    entries.update(row['registration'] for row in ledger.get('active_rollouts', []))
    retained = set()
    registrations = {}
    for entry in entries:
        folder = (ROOT/entry).resolve()
        if folder.parent != REGISTRATIONS.resolve():
            fail(f'mechanism registration is outside the maintained directory: {entry}')
        path, seal_path = folder/'registration.json', folder/'registration-seal.json'
        if not path.is_file() or not seal_path.is_file():
            fail(f'mechanism registration lacks sealed inputs: {entry}')
        value = json.loads(path.read_text())
        if (json.loads(seal_path.read_text()).get('sha256') != hashlib.sha256(path.read_bytes()).hexdigest()
                or value.get('mechanism_contract', {}).get('path_validation') != 'passed'):
            fail(f'mechanism registration or path seal differs: {entry}')
        retained.add(str(folder.relative_to(ROOT)))
        registrations[entry] = value
    for row in workloads:
        entry = row['registration']
        evidence = row.get('current_input_evidence', {})
        if (row.get('current_input_registration') != entry
                or evidence.get('registration', entry) != entry):
            fail(f'current input points to conflicting registrations: {row["id"]}')
        contract = registrations[entry]['mechanism_contract']
        if contract['mechanism'] != row['mechanism']:
            fail(f'current input mechanism differs from its case: {row["id"]}')
        for field in ('world_sha256', 'subject_sha256'):
            if (row['current_' + field] != contract[field]
                    or evidence.get(field, contract[field]) != contract[field]):
                fail(f'current input {field} differs from its positive case: {row["id"]}')
        expected_seal = evidence.get('registration_sha256')
        if expected_seal and expected_seal != hashlib.sha256(
                (ROOT/entry/'registration.json').read_bytes()).hexdigest():
            fail(f'current evidence seal differs from its positive case: {row["id"]}')
    return retained


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
    review = status['formation_reference_validation']
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
    if (release.get('index') != str(path.relative_to(ROOT / 'swarmharm/docs/research'))
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
    contract = json.loads(CONTRACT.read_text())
    status = json.loads(REPORTING.read_text())
    active = json.loads(ACTIVE_STATUS.read_text())

    if contract.get("active_scope") != "continuous-unified":
        fail("retained reporting contract must preserve the continuous unified input")
    if status.get("active_scope") != "continuous-unified" or status.get('study_mode') != 'unified':
        fail("retained reporting status differs from its continuous input")

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

    archived = set(status["maintained_registrations"])
    current = set(active["maintained_registrations"])
    if current & archived:
        fail("a retained reporting registration is also indexed as an active SwarmForm input")
    actual = {
        str(path.relative_to(ROOT)) for folder in REGISTRATION_ROOTS for path in folder.iterdir()
        if path.is_dir() and (path / "registration.json").is_file()
    }
    prefix = active.get("frozen_registration_prefix")
    if prefix != "swarmform-":
        fail("frozen SwarmForm registration prefix differs")
    frozen = {name for name in actual - archived - current
              if Path(name).name.startswith(prefix)}
    if len(frozen) != active.get("frozen_registration_count"):
        fail("frozen SwarmForm registration count differs")
    for name in frozen:
        folder = ROOT / name
        seal_path = folder / "registration-seal.json"
        if not seal_path.is_file():
            fail(f"frozen registration lacks a seal: {name}")
        seal = json.loads(seal_path.read_text())
        if seal.get("sha256") != hashlib.sha256((folder / "registration.json").read_bytes()).hexdigest():
            fail(f"frozen registration seal differs: {name}")
    expected = archived | current | frozen | retained_case_registrations() | mechanism_registrations()
    if actual != expected:
        fail(f"maintained registrations differ: {sorted(actual ^ expected)}")
    if contract["registration_index"] != str(REPORTING.relative_to(ROOT)):
        fail("reporting admission and registration index differ")

    validate_readiness(contract, status)
    validate_phase1_results(contract, status)
    print("Reporting baseline: sealed registration inventory and original case evidence aligned")


if __name__ == "__main__":
    main()
