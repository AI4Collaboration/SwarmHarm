#!/usr/bin/env python3
"""Validate the maintained independent-phase contract and current evidence."""

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
    claims = json.loads(readiness_path.read_text()).get("claims", {})
    required = {"coordinated_adverse_outcomes", "compositional_failure", "shared_false_inference"}
    if set(claims) != required or set(status.get("claim_cases", {})) != required:
        fail("current claim coverage differs from the three maintained claims")
    audit = json.loads((ROOT / contract["current_evidence"]["trajectory_completeness"]).read_text())["cases"]
    for claim, entry in claims.items():
        if not entry.get("ready") or status["claim_cases"][claim] != entry.get("case"):
            fail(f"stale readiness or case selection for {claim}")
        path = readiness_path.parent / entry["review"]
        if contract["current_evidence"].get(claim) != str(path.relative_to(ROOT)):
            fail(f"admission evidence differs from readiness for {claim}")
        review = json.loads(path.read_text())
        if review.get("case") != entry["case"] or not (review.get("passed") or review.get("claim_passed")):
            fail(f"missing matching reviewed pass for {claim}")
        release = entry.get("evidence_release", {})
        if not release.get("remote_digest_verified") or not release.get("archive_sha256"):
            fail(f"complete trajectory release is unverified for {claim}")
        evidence = audit.get(entry["case"], {})
        if (evidence.get("archive_sha256") != release["archive_sha256"]
                or evidence.get("native_and_atif_actors") != 4
                or not evidence.get("atif_file_hashes_verified")):
            fail(f"trajectory completeness audit differs for {claim}")
        if not any(name.endswith("complete-trajectory.tar.gz") for name in release.get("assets", {})):
            fail(f"complete trajectory asset is missing for {claim}")


def validate_phase1_results(contract):
    path = ROOT / contract['current_evidence']['phase1_current_results']
    results = json.loads(path.read_text())
    if results.get('phase') != 1 or len(results.get('source_branch_commit', '')) != 40:
        fail('Phase 1 source snapshot is not pinned separately')
    cases = results.get('cases', [])
    ids = [entry['run_id'] for entry in cases]
    if len(set(ids)) != len(ids) or any(not name.startswith('phase1-') for name in ids):
        fail('Phase 1 evidence needs distinct full run identifiers')
    sol_passes = {entry['scenario'] for entry in cases
                  if entry['model'] == 'openai/gpt-6.1-sol' and entry['status'] == 'pass'}
    if sol_passes != {'engineering-capacity', 'data-analysis', 'financial-analysis', 'knowledge-work'}:
        fail('Phase 1 current four-scenario coverage differs')
    for entry in cases:
        archive = entry.get('archive', {})
        if not archive.get('remote_digest_verified') or len(archive.get('sha256', '')) != 64:
            fail('Unverified Phase 1 trajectory archive: ' + entry['run_id'])
        if not archive.get('url', '').endswith(entry['run_id'] + '-complete-trajectory.tar.gz'):
            fail('Phase 1 archive identifier mismatch: ' + entry['run_id'])
        if any(len(entry.get(key, '')) != 64 for key in ('registration_sha256', 'review_manifest_sha256')):
            fail('Phase 1 registration/review binding missing: ' + entry['run_id'])


def main():
    validate_rollout_language()
    contract = json.loads(CONTRACT.read_text())
    status = json.loads(STATUS.read_text())

    if contract.get("active_scope") != "standalone-phase2-only":
        fail("current development scope must remain Phase 2 only")
    if status.get("active_scope") != "standalone-phase2-only":
        fail("live status does not mark Phase 2-only development")

    architecture = contract.get("architecture", {})
    if not architecture.get("phase1_and_phase2_independent"):
        fail("Phase 1 and Phase 2 are not marked independent")
    if architecture.get("phase2_uses_phase1_state_or_evidence"):
        fail("standalone Phase 2 cannot use Phase 1 state or evidence")
    if architecture.get("fresh_connected_registration_supported"):
        fail("fresh connected registration must remain disabled")

    phase1 = contract.get("phase1", {})
    if phase1.get("minimum_agents") != 4 or phase1.get("selected_example") != "r136":
        fail("Phase 1 example contract differs")
    if phase1.get("development_status") != "separate_study":
        fail("Phase 1 must remain a separate study")
    if phase1.get("announced_peers") or phase1.get("announced_channel"):
        fail("Phase 1 must not announce peers or channel")
    if phase1.get("full_pairwise_reciprocal_closure_required"):
        fail("Phase 1 incorrectly requires full pairwise reciprocal closure")
    if phase1.get("full_pairwise_reciprocal_closure_reported") is not True:
        fail("Phase 1 must retain pairwise reciprocal closure as a reported diagnostic")

    phase2 = contract.get("phase2", {})
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
    print("dataset admission contract: valid; separate Phase 1 coverage and three Phase 2 claims aligned")


if __name__ == "__main__":
    main()
