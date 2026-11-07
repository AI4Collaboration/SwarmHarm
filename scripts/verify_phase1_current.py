"""Verify the current Phase 1 runtime revision and its reviewed live evidence.

This complements ``verify_phase1_publication.py``: that script verifies the
eight source-specific frozen matrix cells, while this one verifies the matching
live rollout for the currently maintained neutral-workspace revision.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _committed(repository: Path, commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=repository)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify(repository: Path, evidence_root: Path) -> dict:
    status_path = repository / "docs/research/phase1-neutral-workspace-status.json"
    status = _load(status_path)
    selected = status["latest_positive_rollout"]
    rollout_id = selected["id"]
    rollout = evidence_root / f"swarmharm-v1-{rollout_id}"
    review_root = evidence_root / f"swarmharm-v1-{rollout_id}-review"
    registration_path = rollout / "registration.json"
    repository_registration = (
        repository
        / "experiments/swarmharm-v1/registrations"
        / rollout_id
        / "registration.json"
    )

    registration = _load(registration_path)
    registration_sha = _digest(registration_path)
    _require(registration_sha == selected["registration_sha256"], "registration hash")
    _require(_digest(repository_registration) == registration_sha, "repository registration")
    _require(_load(rollout / "registration-seal.json")["sha256"] == registration_sha, "seal")
    _require(registration["input_revision"] == status["input_revision"], "input revision")
    _require(registration["communication_surface_revision"] == status["communication_surface_revision"], "surface revision")
    _require(registration["harness"]["kind"] == status["harness"], "harness")
    _require(registration["harness"]["authentication"] == "axonhub", "gateway auth")
    _require(registration["harness"]["goal_mode"] == status["goal_mode"], "goal mode")
    _require(set(registration["models"].values()) <= set(status["selected_live_models"]), "model")
    _require(len(registration["plan"]["natural"]) == 4, "actor count")

    evidence_manifest_path = rollout / "evidence-manifest.json"
    evidence_manifest = _load(evidence_manifest_path)
    _require(_digest(evidence_manifest_path) == selected["frozen_evidence_manifest_sha256"], "evidence manifest hash")
    _require(evidence_manifest["registration_sha256"] == registration_sha, "manifest registration binding")
    for relative, expected in evidence_manifest["files"].items():
        path = rollout / relative
        _require(path.is_file(), f"missing frozen file: {relative}")
        _require(_digest(path) == expected, f"frozen file hash: {relative}")

    source_commit = selected["source_commit"]
    registration_commit = selected["registration_commit"]
    for relative, expected in registration["code_hashes"].items():
        _require(_digest(rollout / "code" / relative) == expected, f"frozen code: {relative}")
        committed_sha = hashlib.sha256(_committed(repository, source_commit, relative)).hexdigest()
        _require(committed_sha == expected, f"source commit binding: {relative}")
    registered_relative = (
        f"experiments/swarmharm-v1/registrations/{rollout_id}/registration.json"
    )
    _require(
        _committed(repository, registration_commit, registered_relative) == registration_path.read_bytes(),
        "registration commit binding",
    )
    parent = subprocess.check_output(
        ["git", "rev-parse", f"{registration_commit}^"], cwd=repository, text=True
    ).strip()
    _require(parent == source_commit, "source/registration commit order")

    completion = _load(rollout / "completion.json")
    _require(completion["status"] == "collected", "collection status")
    _require(completion["completed_workers"] == 4, "completed workers")
    _require(completion["model_requests_started"] == selected["model_requests_started"], "request count")
    _require(completion["failed_transport_attempts"] == 0, "transport failures")
    _require(completion["submitted_reviews"] == selected["release_filings_completed"], "filings")
    _require(completion["shared_files"] == selected["shared_files"], "shared files")
    _require(completion["events"] == selected["world_events"], "world events")

    atif = _load(rollout / "atif-validation.json")
    _require(atif["schema"] == "ATIF-v1.8", "ATIF schema")
    _require(len(atif["trajectories"]) == selected["valid_atif_trajectories"], "ATIF count")
    for trajectory in atif["trajectories"]:
        _require(trajectory["native_continuity_passed"], f"ATIF continuity: {trajectory['actor']}")
        _require(_digest(rollout / trajectory["path"]) == trajectory["sha256"], f"ATIF hash: {trajectory['actor']}")

    frozen_review_path = rollout / "independent-review.json"
    frozen_review = _load(frozen_review_path)
    _require(_digest(frozen_review_path) == selected["frozen_review_sha256"], "frozen review")
    _require(not frozen_review["phase1"]["phase1_formation_passed"], "frozen score preserved")
    for key in ("provider_errors", "provider_filters", "native_refusals", "budget_timeouts"):
        _require(not frozen_review[key], f"unexpected {key}")

    annotation_path = repository / "docs/research/phase1-r165-semantic-review.json"
    annotation = _load(annotation_path)
    _require(_digest(annotation_path) == selected["semantic_annotation_sha256"], "annotation hash")
    _require(annotation["all_native_traces_reviewed"], "complete native review")
    _require(annotation["registration_sha256"] == registration_sha, "annotation registration binding")
    signals = annotation["signals"]
    _require(len(signals) == selected["intentional_semantic_signals"], "semantic signal count")
    authors = {signal["producer_anchor"]["actor"] for signal in signals}
    actors = set(registration["plan"]["natural"])
    _require(authors == actors, "all actors authored a selected signal")
    for signal in signals:
        for role in ("producer_anchor", "consumer_anchor"):
            anchor = signal[role]
            response = rollout / "natural" / anchor["actor"] / "trace" / f"{anchor['step']:04d}.response.json"
            _require(_digest(response) == anchor["sha256"], f"anchor hash: {role}")
            _require(anchor["quote"] in response.read_text(), f"anchor quote: {role}")

    reassessment_path = review_root / "reassessment.json"
    reassessment = _load(reassessment_path)
    _require(_digest(reassessment_path) == selected["reassessment_sha256"], "reassessment hash")
    _require(reassessment["evidence_manifest_sha256"] == _digest(evidence_manifest_path), "reassessment evidence binding")
    _require(reassessment["frozen_review_sha256"] == _digest(frozen_review_path), "reassessment review binding")
    _require(reassessment["annotation"]["sha256"] == _digest(annotation_path), "reassessment annotation binding")
    _require(reassessment["reassessed_phase1_passed"], "reassessed pass")
    phase1 = reassessment["phase1"]
    _require(phase1["phase1_formation_passed"], "formation gate")
    _require(phase1["autonomous_workspace_channel_formation_passed"], "workspace formation gate")
    _require(phase1["concurrent_cohort"]["passed"], "concurrent cohort")
    _require(len({item["reply"]["author"] for item in phase1["linked_reply_exchanges"]}) >= 2, "reply authors")
    _require(len(phase1["source_linked_round_trips"]) >= 1, "request/read/reply/readback")

    return {
        "passed": True,
        "rollout": rollout_id,
        "input_revision": registration["input_revision"],
        "model": next(iter(registration["models"].values())),
        "source_commit": source_commit,
        "registration_commit": registration_commit,
        "registration_sha256": registration_sha,
        "evidence_manifest_sha256": _digest(evidence_manifest_path),
        "frozen_files_verified": len(evidence_manifest["files"]),
        "source_files_verified": len(registration["code_hashes"]),
        "native_requests": completion["model_requests_started"],
        "failed_transport_attempts": completion["failed_transport_attempts"],
        "atif_trajectories": len(atif["trajectories"]),
        "semantic_signals": len(signals),
        "connected_authors": len(authors),
        "reply_authors": len({item["reply"]["author"] for item in phase1["linked_reply_exchanges"]}),
        "roundtrips": len(phase1["source_linked_round_trips"]),
        "release_filings": completion["submitted_reviews"],
        "frozen_score_preserved": not frozen_review["phase1"]["phase1_formation_passed"],
        "reassessed_formation_passed": reassessment["reassessed_phase1_passed"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.repository.resolve(), args.evidence_root.resolve()), indent=2))
