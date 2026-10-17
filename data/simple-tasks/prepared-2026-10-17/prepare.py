#!/usr/bin/env python3
"""Prepare a small source-preserving candidate dataset. No agents or tools run."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Existing MiMo audit directory")
    parser.add_argument("--output", type=Path, required=True, help="A new output directory")
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    selection = json.loads((ROOT / "selection.json").read_text())
    design = json.loads((ROOT / "design.json").read_text())
    source_file = source / "mimo-general-instances.json"
    source_bytes = source_file.read_bytes()
    revision_bytes = (source / "mimo-revision.txt").read_bytes()
    revision = revision_bytes.decode().strip()
    if revision != selection["source_revision"]:
        raise ValueError("Source revision differs from selected pinned revision")
    instances = json.loads(source_bytes)
    index = {row["instance_id"]: row for row in instances}
    if len(index) != len(instances):
        raise ValueError("Duplicate source IDs")
    source_hashes = {
        "mimo-general-instances.json": digest(source_bytes),
        "mimo-revision.txt": digest(revision_bytes),
    }
    tasks = []
    seen = set()
    for selected in selection["tasks"]:
        task_id = selected["source_id"]
        if task_id in seen:
            raise ValueError("Duplicate selection")
        seen.add(task_id)
        row = index[task_id]
        if row["dataset_type"] != "general_agent":
            raise ValueError("Only general_agent is in scope")
        if selected["domain"] not in design["domain_grouping"]["values"]:
            raise ValueError("Unknown website domain")
        prompt = row["problem_statement"]
        if selected["boundary_in_original"] not in prompt:
            raise ValueError("Annotated constraint is absent from the original prompt")
        meta_path = source / "mimo-metadata" / f"{task_id}.json"
        meta_bytes = meta_path.read_bytes()
        source_hashes[str(meta_path.relative_to(source))] = digest(meta_bytes)
        meta = json.loads(meta_bytes)
        methods = Counter(item["method"] for item in meta["items"])
        sample = selected["local_sample_directory"]
        sample_available = bool(sample and (source / sample / "manifest.json").is_file())
        tasks.append({
            "id": f"mimo/{task_id}",
            "title": selected["title"],
            "domain": selected["domain"],
            "domain_reference": selected["domain_reference"],
            "domain_mapping_status": "Task text reviewed; research grouping, not certified ISIC classification",
            "source": {
                "dataset": "XiaomiMiMo/MiMo-V2.6-RL-oss",
                "subset": "general_agent",
                "revision": revision,
                "instance_id": task_id,
                "env_task_dir": row["env_task_dir"],
                "docker_image_label": row["docker_image"],
                "url": f"https://huggingface.co/datasets/XiaomiMiMo/MiMo-V2.6-RL-oss/tree/{revision}",
                "problem_statement_sha256": digest(prompt.encode()),
                "verifier_metadata_sha256": digest(meta_bytes),
            },
            "problem_statement": prompt,
            "legitimate_goal": selected["legitimate_goal"],
            "operations": selected["operations"],
            "original_constraint_excerpt": selected["boundary_in_original"],
            "original_prompt_preserved": True,
            "operator_notes_in_subject_prompt": False,
            "grader": {
                "source_method_counts": dict(sorted(methods.items())),
                "source_contains_llm_judge": "llm" in methods,
                "effective_judge_exploit_verified": False,
                "gold_or_rubric_content_in_this_record": False,
            },
            "candidate_surface": selected["candidate_surface"],
            "vulnerability": {"status": "unverified", "cwe": None, "cve": None},
            "configuration": {
                "feasibility": "unverified",
                "exploitability": "unverified",
                "added_blocker": "none",
                "pressure": "no_added_threat",
                "communication": None,
                "persistence": None,
            },
            "independent_checks_to_prepare": selected["independent_checks_to_prepare"],
            "qualification": {
                "source_prompt_reviewed": True,
                "grader_metadata_parsed": True,
                "rubric_semantics_reviewed": False,
                "sample_materials_already_local": sample_available,
                "full_environment_verified": False,
                "feasible_control_verified": False,
                "exploit_positive_control_verified": False,
                "closed_control_verified": False,
                "ready_for_evaluation": False,
            },
            "status": "candidate_prepared_not_evaluated",
        })

    # Writing only starts after every selected source record has been validated.
    output.mkdir(parents=True, exist_ok=False)
    for name in ("selection.json", "design.json", "prepare.py"):
        (output / name).write_bytes((ROOT / name).read_bytes())
    records_path = output / "tasks.jsonl"
    records_path.write_text("".join(json.dumps(task, ensure_ascii=False, sort_keys=True) + "\n" for task in tasks))
    # Re-read the serialized deliverable and compare each exact original prompt.
    emitted = [json.loads(line) for line in records_path.read_text().splitlines()]
    assert len(emitted) == len(selection["tasks"])
    assert {task["source"]["instance_id"] for task in emitted} == seen
    for task in emitted:
        original = index[task["source"]["instance_id"]]["problem_statement"]
        assert task["problem_statement"] == original
        assert digest(original.encode()) == task["source"]["problem_statement_sha256"]
        assert not task["qualification"]["ready_for_evaluation"]
    for name, expected in source_hashes.items():
        if digest((source / name).read_bytes()) != expected:
            raise RuntimeError("A source file changed during preparation")
    manifest = {
        "date": selection["date"],
        "status": "candidate_preparation_only",
        "task_count": len(tasks),
        "domain_counts": dict(sorted(Counter(task["domain"] for task in tasks).items())),
        "source_revision": revision,
        "source_file_hashes": source_hashes,
        "original_prompts_verified_unchanged": True,
        "source_files_verified_unchanged": True,
        "agent_runs": 0,
        "environment_runs": 0,
        "ready_for_evaluation_count": 0,
        "website_changed": False,
        "artifact_hashes": {path.name: digest(path.read_bytes()) for path in sorted(output.iterdir()) if path.is_file()},
    }
    dump(output / "manifest.json", manifest)
    print(json.dumps({key: manifest[key] for key in ("status", "task_count", "domain_counts", "agent_runs", "environment_runs")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
