"""Repair only the missing aggregate cleanup export; never rerun a subject."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def repair(root):
    assert not (root / "current-review-status.json").exists(), "Already reviewed; do not repeat analysis without a new reason"
    reg, review, completion = (load(root / name) for name in
        ("registration.json", "independent-review.json", "completion.json"))
    assert review["integrity_passed"] and review["all_natural_workers_completed"] and review["independent_gate_passed"]
    assert not review["errors"] and not (root / "cleanup-summary.json").exists()
    requests = sorted(root.rglob("*.request.json"))
    for path in requests:
        assert path.with_name(path.name.replace(".request.json", ".response.json")).exists(), path
    archive = root / "analysis-repair/initial"
    archive.mkdir(parents=True, exist_ok=False)
    for path in [root / "independent-review.json", root / "authored-text-evidence.json",
                 root / "completion.json", *root.glob("*-execution.json")]:
        if path.exists():
            shutil.copyfile(path, archive / path.name)
    receipts = {}
    for cell in [reg["calibration"], *reg["cells"]]:
        path = root / cell["id"] / "cleanup.json"
        assert load(path)["provider_live"] is False
        receipts[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    save(root / "cleanup-summary.json", {"finished_at": completion["finished_at"],
        "exported_at": datetime.now(timezone.utc).isoformat(), "generated_after_collection": True,
        "owned_provider_futures_complete": True, "actor_statuses": completion["actor_statuses"],
        "new_credentials_or_cloud_resources": 0, "hosted_runtime_changed": False,
        "cleanup_receipts_sha256": receipts,
        "repair_reason": "Missing aggregate marker; complete world cleanup receipts and matched request/response records were already present. Initial failed reviews are preserved. No model retry."})
    executions = []
    for script in ("hf-method-v2/review.py", "hf-method-analysis/policy_exposure.py",
                   "hf-method-analysis/handoff.py", "hf-method-analysis/output_quality.py"):
        result = subprocess.run([sys.executable, str(REPO / "experiments" / script), "--output", str(root)],
                                capture_output=True, text=True, cwd=REPO)
        executions.append({"script": script, "exit_code": result.returncode,
                           "stdout": result.stdout, "stderr": result.stderr})
        save(root / "analysis-repair/executions.json", executions)
        assert result.returncode == 0, script
    assert sorted(root.rglob("*.request.json")) == requests
    assert load(root / "independent-review.json")["passed"]
    assert load(root / "output-quality.json")["passed"]
    save(root / "current-review-status.json", {"updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "reviewed_after_cleanup_export", "independent_review_passed": True,
        "output_quality_passed": True, "source_and_trajectory_unchanged": True, "new_model_calls": 0,
        "original_collector_status_preserved_in": "completion.json",
        "original_failed_review_outputs_preserved_in": "analysis-repair/initial"})
    print(json.dumps({"review_repaired": True, "model": reg["model"], "new_model_calls": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    repair(parser.parse_args().output.resolve())
