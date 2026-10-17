#!/usr/bin/env python3
"""Offline cross-export accounting; never launches a subject or repairs evidence.

Existing exact replay/semantic qualification records are preserved. This review
checks their code dependencies and counts *all* provider replies, including the
failed initial qualification and separately instructed functionality controls.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COHORTS = ["reciprocal-01", "proxy-controls-01", "staging-delayed-01", "staging-02", "round-03",
           "route-check-sol-01", "round-02", "round-01", "route-check-01"]


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def review(root):
    spec = importlib.util.spec_from_file_location("archive_trace_core", REPO / "experiments/hf-campaign-v1/review.py")
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    errors, cohorts, totals = [], [], Counter()
    for name in COHORTS:
        folder = root / name
        if not folder.exists():
            errors.append(name + ": missing assigned export")
            continue
        route_only = name.startswith("route-check")
        if route_only:
            summary = load(folder / "preflight/summary.json")
            reg = {"model": summary["model"], "reasoning": summary["reasoning"]}
            assert summary["passed"] and summary["native_roundtrip"]
        else:
            reg = load(folder / "registration.json")
            assert sha(folder / "registration.json") == load(folder / "registration-seal.json")["sha256"], name
            for relative, expected in reg.get("code_hashes", reg.get("runtime_inputs", {})).items():
                assert sha(folder / "code" / relative) == expected, (name, relative)
            for relative, expected in reg.get("input_hashes", {}).items():
                assert sha(folder / relative) == expected, (name, relative)
        counts, provider_times = Counter(), []
        requests = sorted(folder.rglob("*.request.json"))
        for path in requests:
            response_path = path.with_name(path.name.removesuffix(".request.json") + ".response.json")
            response = load(response_path) if response_path.exists() else None
            core.provider_check(load(path), response, reg, str(path.relative_to(root)), errors, counts)
            if response is not None:
                provider_times.append(response["created_at"])
        assert len(list(folder.rglob("*.response.json"))) == counts["response_files"], name
        record = {"cohort": name, "model": reg["model"], "reasoning": reg["reasoning"],
                  "provider_counts": dict(counts), "natural_confirmatory_estimate": False,
                  "latest_provider_response_created_at": max(provider_times)}
        if (folder / "independent-review.json").exists():
            audit = load(folder / "independent-review.json")
            assert audit["integrity_passed"] and audit["collection_complete"], name
            assert audit["original_gate_passed"] and audit["independent_gate_passed"], name
            if name.startswith(("staging-", "reciprocal-")):
                assert 'SQLite' in audit.get('source_reference_method',''), name
            source = audit["analysis_code"]
            assert sha(folder / source["path"]) == source["sha256"], name
            assert audit.get("analysis_dependencies"), name
            for dep in audit["analysis_dependencies"]:
                assert sha(folder / dep["path"]) == dep["sha256"], name
            expected_count = sum(p.get("verified_responses", 0) for p in audit["provider_counts"].values())
            assert counts["verified_responses"] == expected_count, name
            worlds = [w for w in audit["worlds"] if w["phase"] == "natural"]
            actors = [a for a in audit["actors"] if a["phase"] == "natural"]
            assert len(worlds) == len(reg["cells"]) and all(w["completed_export"] for w in worlds), name
            record.update({"kind": "adaptive_natural_development", "qualified": audit["passed"],
                "measurement_qualification": audit["measurement_qualification"],
                "source_reference_method": audit.get("source_reference_method", "Pinned per-case references"),
                "independent_worlds": len(worlds), "natural_actors": len(actors),
                "completed_natural_actors": sum(a["status"] == "completed" for a in actors),
                "natural_responses": audit["provider_counts"]["natural"]["verified_responses"],
                "natural_tools": audit["provider_counts"]["natural"]["tool_trace_files"],
                "natural_protected_source_reads": sum(a["protected_source_reads"] for a in actors),
                "natural_receipt_mutations": sum(a.get("receipt_mutations", 0) for a in actors),
                "worlds": [{k: w.get(k) for k in ("world", "mode", "channel", "elapsed_seconds", "peer_artifact_read_operations", "shared_text_writes", "effect_events")} for w in worlds]})
            assert load(folder / "cleanup-summary.json")["owned_provider_futures_complete"], name
        elif name == "round-01":
            gate = load(folder / "gate.json")
            actors = load(folder / "calibration/results.json")
            assert not gate["passed"] and len(actors) == 4, name
            assert all(a["status"] == "episode_error" and a["error"] == "No module named 'jsonschema'" for a in actors), name
            assert not (folder / "natural-started.json").exists(), name
            assert not any((folder / cell["id"]).exists() for cell in reg["cells"]), name
            assert len(list((folder / "calibration").rglob("*.request.json"))) == 4, name
            assert not list((folder / "calibration").rglob("*-tool-*.json")), name
            assert load(folder / "calibration/cleanup.json")["provider_live"] is False, name
            record.update({"kind": "failed_infrastructure_qualification", "qualified": False,
                "original_gate_passed": False, "natural_worlds_started": 0, "calibration_failed_actors": 4,
                "successful_calibration_tool_dispatches": 0,
                "limit": "Provider identity and sealed inputs checked; missing tool results make a successful native-tool/history qualification impossible. Failure is retained, not repaired."})
        elif name == "proxy-controls-01":
            summary = load(folder / "summary.json")
            assert summary["assigned"] == 2 and summary["completed"] == 2 and summary["integrity_passed"], name
            assert summary["provider_counts"]["verified_responses"] == counts["verified_responses"], name
            assert not summary["natural_trial"], name
            record.update({"kind": "explicitly_instructed_functionality", "qualified": summary["integrity_passed"],
                           "functionality_passes": summary["functionality_passes"], "assigned": 2,
                           "natural_trial": False})
        else:
            assert route_only, name
            record.update({"kind": "native_route_probe", "qualified": True, "natural_trial": False})
        credential = core.credential_findings(folder)
        if not credential["passed"]:
            errors.append(name + ": recognizable plaintext credential candidate")
        record["credential_scan"] = credential
        cohorts.append(record)
        totals.update(counts)
    assert len(cohorts) == len(COHORTS)
    cohorts.sort(key=lambda c: c["latest_provider_response_created_at"], reverse=True)
    source = Path(__file__).resolve()
    analysis = root / "accounting-code"
    analysis.mkdir(exist_ok=True)
    target = analysis / ("archive-review-" + sha(source)[:16] + ".py")
    target.write_bytes(source.read_bytes())
    core_source = REPO / "experiments/hf-campaign-v1/review.py"
    core_target = analysis / ("trace-review-" + sha(core_source)[:16] + ".py")
    core_target.write_bytes(core_source.read_bytes())
    result = {"passed": not errors, "model_requests_made_by_review": 0, "cohorts_latest_first": cohorts,
        "provider_counts_all_categories": dict(totals), "errors": errors,
        "analysis_code": [{"path": str(p.relative_to(root)), "sha256": sha(p)} for p in (target, core_target)],
        "claim_limits": ["Accounting totals are not pooled behavioral rates", "Failed and semantic-quality-failed rounds retained",
                         "Actors and repeated reads are correlated within each world", "No inferred intent, method transfer, causal contagion or long human-time autonomy"]}
    save(root / "archive-accounting.json", result)
    print(json.dumps({"passed": result["passed"], "provider_counts": dict(totals), "errors": errors}))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    review(p.parse_args().output.resolve())
