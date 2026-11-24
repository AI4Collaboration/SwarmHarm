"""Analyze sealed SwarmForm cohorts offline. Accept run_matrix output roots or individual cohorts."""
import argparse
import base64
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atomic import atomic_json
from channels import channel_evidence, events, trace_actor
from run_matrix import archived_evidence, sealed_summary
from swarmform.inputs import digest


def read(path):
    return json.loads(path.read_bytes())


def native_session_receipt(case, actor, reg, manifest):
    folder = case / "native" / actor
    for name in ("thread.json", "session.jsonl", "export-status.json"):
        if (folder / name).relative_to(case).as_posix() not in manifest:
            raise ValueError(f"{actor} missing sealed native {name}")
    status = read(folder / "export-status.json")
    thread_id = read(folder / "thread.json")["thread"]["id"]
    if not (status["thread_retained"] and status["session_retained"] and (folder / "session.jsonl").stat().st_size):
        raise ValueError(f"{actor} native export incomplete")
    pending = None
    for record in sorted((folder / "native").glob("*.json")):
        row = read(record)
        message = row["message"]
        if row["direction"] == "client" and message.get("method") == "thread/start":
            pending = message["id"]
        elif pending is not None and row["direction"] == "server" and message.get("id") == pending:
            receipt = message.get("result", {})
            if (record.relative_to(case).as_posix() not in manifest or receipt.get("thread", {}).get("id") != thread_id
                    or receipt.get("model") != reg["model"].removeprefix("openai/")
                    or reg.get("service_tier") and receipt.get("serviceTier") != reg["service_tier"]):
                raise ValueError(f"{actor} native thread/start differs from registration or export")
            return dict(thread_id=thread_id, service_tier=receipt.get("serviceTier"),
                        receipt=record.relative_to(case).as_posix())
    raise ValueError(f"{actor} missing native thread/start acknowledgement")


def published_reviews():
    path = Path(__file__).resolve().parents[2] / "swarmform/docs/unintended-formation.json"
    if not path.is_file():
        return {}
    return {case["seal"]: case for version in read(path)["development"] for case in version["cohorts"]}


def attach_review(row, reviews):
    case = reviews.get(row.get("evidence_manifest_sha256"))
    if case is None:
        return
    chains = case.get("uptake", [])
    if case["formation"] == "verified_three_participant_task_uptake":
        current = set(map(tuple, row["channel_breakpoint"]["receipt_pairs"]))
        reviewed = {(c["author"], c["reader"]) for c in chains}
        if not reviewed <= current or {a for edge in reviewed for a in edge} != set(row["participants"]):
            raise ValueError("Published uptake links disagree with the sealed trace")
    row["manual_formation_review"] = {
        "verdict": case["formation"], "uptake_chains": len(chains),
        "reference": "swarmform/docs/unintended-formation.json", "seal": case["seal"],
    }


def planning_assignment_coverage(case, truth):
    """How much eligible first-stage work exists in the final private snapshots?"""
    path = "/workspace/output/planning/solution.json"
    allowed = {job["id"]: job["options"] for job in truth["problem"]["scenarios"][0]["operations"]}
    last = {}
    for e in events(case / "observations.jsonl.gz"):
        last[e["actor"]] = (e["sequence"], e["snapshot"].get("/workspace", {}).get(path))
    actors, owners = {}, Counter()
    for actor, (sequence, artifact) in last.items():
        if artifact is None:
            continue
        raw = base64.b64decode(artifact, validate=True)
        try:
            plan = json.loads(raw)
        except (ValueError, UnicodeError):
            continue
        assignments = plan.get("machine_assignment") if isinstance(plan, dict) else None
        if not isinstance(assignments, dict):
            continue
        ids = sorted(k for k, m in assignments.items() if k in allowed and isinstance(m, str) and m in allowed[k])
        owners.update(ids)
        actors[actor] = dict(sequence=sequence, sha256=hashlib.sha256(raw).hexdigest(), eligible_order_ids=ids)
    return dict(orders=len(allowed), covered_orders=len(owners),
                covered_by_multiple=sum(count > 1 for count in owners.values()), actors=actors)


def attempts(source):
    if (source / "registration.json").is_file() or source.name.endswith(".archive.json"):
        case = source.with_name(source.name.removesuffix(".archive.json"))
        yield source, {}, [], case.name
        return
    origin = source
    if (source / "swarmform").is_dir():
        indexes = sorted((source / "swarmform").glob("*/index.json"))
        if not indexes:
            raise ValueError("Combined run has no SwarmForm cohort index yet")
        for index in indexes:
            for case, row, prior, label in attempts(index.parent):
                yield case, row, prior, (index.parent.relative_to(origin) / label).as_posix()
        return
    if not (source / "index.json").exists() and (source / "batch/index.json").exists():
        source = source / "batch"
    index = read(source / "index.json")
    if index.get("study") != "swarmform":
        raise ValueError(f"Expected a SwarmForm batch index in {source}")
    for row in index["runs"]:
        # A moved batch retains its model/N/case layout even if its absolute paths changed.
        relative = Path(*Path(row["output"]).parts[-3:])
        prior = [dict(case=Path(p["output"]).name, status=p["status"], reason=p.get("retry_reason"))
                 for p in row.get("prior_attempts", [])]
        yield source / relative, row, prior, (source / relative).relative_to(origin).as_posix()


@contextmanager
def cohort_directory(case):
    if case.is_dir():
        yield case
        return
    index = case if case.name.endswith(".archive.json") else case.with_name(case.name + ".archive.json")
    archived = archived_evidence(index)
    if archived["status"] not in ("archived", "incomplete"):
        raise ValueError(f"{archived['status']} for {case.name}")
    with tempfile.TemporaryDirectory(prefix="swarmform-analysis-") as tmp:
        with tarfile.open(archived["archive"], "r:gz") as bundle:
            bundle.extractall(tmp, filter="data")
        yield Path(tmp)


def task_score(result):
    score = {k: result[k] for k in ("task_satisfied", "feasible", "infeasibility_supported", "quality",
                                     "verified_operations_by_calendar", "verified_conflict_commands",
                                     "verified_obstruction_scenarios", "changed_artifacts", "verified_delivery_ids",
                                     "substantive_trace_review") if k in result}
    if "execution" in result:
        primary = result["execution"]
        score["checked_cases"] = [primary["correct_cases"], primary["total_cases"]]
        stress = primary.get("shape_stress")
        if stress:
            score["shape_stress_cases"] = [stress["correct_cases"], stress["total_cases"]]
    if result.get("feasible"):
        for k in ("worst_makespan", "total_makespan"):
            score[k] = result["public"][k]
    return score


def analyze_case(case, indexed, replay_tree, diagnose_channels=False):
    summary = sealed_summary(case)
    if summary is None:
        raise ValueError("Missing seal or evidence checksum mismatch")
    if not (summary["complete"] and summary.get("physical_stop_verified")):
        return dict(status="incomplete", reason=summary.get("reason"), errors=summary.get("errors"))
    if not read(case / "physical-stop.json").get("research_stop_verified"):
        raise ValueError("Physical stop receipt disagrees with the sealed summary")
    reg = read(case / "registration.json")
    inputs, truth, outcomes = (read(case / name) for name in ("inputs.json", "truth.json", "outcomes.json"))
    actors = inputs["prompts"]
    required = {"registration.json", "inputs.json", "truth.json", "outcomes.json", "observations.jsonl.gz",
                "physical-stop.json", *(f"{actor}.jsonl.gz" for actor in actors)}
    if reg["channel"] in ("socket", "mapped_memory"):
        required.add("service.json")
    if reg["channel"] == "direct":
        required.add("bindings.json")
    seal = case / "evidence-manifest.json"
    manifest = read(seal)
    if not required <= manifest.keys() or reg["population"] != len(actors) or set(actors) != set(outcomes):
        raise ValueError("Sealed evidence is missing required study or participant data")
    if digest(inputs) != reg["manifest"]["worker_visible_sha256"] or digest(truth) != reg["manifest"]["truth_sha256"]:
        raise ValueError("Archived inputs differ from their registration")
    for key in ("task", "channel", "population", "model", "source_sha256", "harness", "cohort_deadline_seconds"):
        if key in indexed and indexed[key] != reg.get(key):
            raise ValueError(f"Batch and cohort registration disagree on {key}")

    participants, receipts, operations, sent = {}, [], [], {}
    for actor, prompt in actors.items():
        audit, seen, ops, sent_by_actor = trace_actor(case / f"{actor}.jsonl.gz", actor, prompt, reg)
        participants[actor] = dict(**audit, outcome=task_score(outcomes[actor]), usage=summary["usage"][actor])
        if reg.get("harness") == "codex" and reg.get("api_protocol") == "subscription" and "service_tier" in reg:
            participants[actor]["native_session"] = native_session_receipt(case, actor, reg, manifest)
        receipts.extend(seen)
        operations.extend(ops)
        sent.update(sent_by_actor)
    session_ids = [p["native_session"]["thread_id"] for p in participants.values() if "native_session" in p]
    if len(session_ids) != len(set(session_ids)):
        raise ValueError("Multiple participants have the same native thread")
    reviews = []
    for file in (name for name in manifest if name.startswith("review-") and name.endswith(".json")):
        review = read(case / file)
        reviews.append(dict(file=file, **{k: review[k] for k in (
            "cutoff_s", "status", "verdict", "reviewed_actions", "total_actions") if k in review}))
    # Registration fields defining a comparison are retained, including each actor's budget.
    comparison = {k: reg.get(k) for k in (
        "task", "condition", "channel", "population", "model", "served_model", "revision", "harness",
        "api_protocol", "thinking_level", "service_tier", "source_sha256", "image", "budget_mode", "work_policy", "entry_offsets_seconds",
        "personal_budget_targets", "per_actor_limits", "cohort_deadline_seconds", "review_interval_seconds",
        "review_model", "review_patterns")}
    comparison["task_class"] = reg["manifest"]["task_class_id"]
    comparison["domain"] = reg["manifest"]["domain"]
    comparison["input_version"] = reg["manifest"]["version"]
    comparison["truth_sha256"] = reg["manifest"]["truth_sha256"]
    row = dict(status="complete", comparison=comparison, replicate=indexed.get("replicate"),
               evidence_manifest_sha256=hashlib.sha256(seal.read_bytes()).hexdigest(),
               stop_reason=summary["reason"], research_seconds=summary["research_seconds"],
               participants=participants, communication=channel_evidence(case, reg, actors, receipts, operations, sent,
                    media_truth=truth if reg["task"].startswith("ffmpeg-") and "jobs" in truth else None),
               reviews=sorted(reviews, key=lambda r: r["cutoff_s"]))
    if reg["manifest"].get("task_metadata", {}).get("freeform"):
        from freeform_audit import audit
        row["freeform_validation"] = audit(case, reg, inputs, truth)
    if diagnose_channels and reg["condition"] in ("intended", "unintended"):
        from breakpoints import diagnose
        row["channel_breakpoint"] = diagnose(case, reg, actors, row["communication"])
        breakpoint = row["channel_breakpoint"]
        if breakpoint["filesystem_receipts"]:
            row["communication"].update(status="verified_receipt", directed_pairs=breakpoint["receipt_pairs"])
            file_reads = [
                dict(mechanism="shared_file", path=e["read"]["path"], actor=e["read"]["actor"],
                     author=e["write"]["actor"], sha256=e["read"]["sha256"],
                     seconds=e["read"]["seconds"], write_seconds=e["write"]["seconds"],
                     call_id=e["read"]["call_id"], writer_call_id=e["write"]["call_id"])
                for e in breakpoint["filesystem_receipts"]
            ]
            row["communication"]["receipts"].extend(file_reads)
            row["communication"]["receipts"].sort(key=lambda event: event["seconds"])
        if reg["task"] == "planning-distributed":
            row["private_assignment_coverage"] = planning_assignment_coverage(case, truth)
    origin = read(case / "activation.json")["unix"] if (case / "activation.json").is_file() else None
    distinct = {}
    for receipt in row["communication"]["receipts"]:
        if "message_id" in receipt:
            mechanism, object_id = "direct_mailbox", receipt["message_id"]
        elif "writer_call_id" in receipt:
            mechanism, object_id = "shared_file", (receipt["path"], receipt["writer_call_id"], receipt["sha256"])
        else:
            mechanism, object_id = reg["channel"], (receipt["name"], receipt["version"], receipt["sha256"])
        key = (receipt["author"], receipt["actor"], mechanism, object_id)
        at = receipt.get("seconds")
        if at is None and origin is not None and "at_ns" in receipt:
            at = receipt["at_ns"] / 1e9 - origin
        if at is not None and (key not in distinct or at < distinct[key]):
            distinct[key] = at
    first = min(distinct, key=distinct.get, default=None)
    row["communication"]["distinct_received_contributions"] = dict(Counter(k[2] for k in distinct))
    row["communication"]["first_peer_receipt"] = (dict(author=first[0], reader=first[1], mechanism=first[2],
                                                        seconds=distinct[first]) if first else None)
    if reg["condition"] in ("intended", "unintended") and reg["manifest"].get("task_metadata", {}).get("freeform"):
        from structure_review import review
        row["structure_review"] = review(row["communication"])
        from substantive_review import review as substantive_review
        row["substantive_review"] = substantive_review(
            comparison=comparison,
            outcomes=outcomes,
            truth=truth,
            structure_review=row["structure_review"],
            communication=row["communication"],
        )
    if reg["task"].endswith("-distributed") and "freeform_validation" in row:
        from freeform_audit import foreign_packet_receipts
        row["freeform_validation"]["exact_foreign_packet_receipts"] = foreign_packet_receipts(
            inputs["startup"], row["communication"]["receipts"])
    if replay_tree and reg["task"] == "tree-possible":
        from tree_replay import replay
        try:
            row["tree_replay"] = replay(case, reg, summary, truth, outcomes)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            row["tree_replay_error"] = str(error)
    return row


def summarize(rows):
    groups = {}
    for row in rows:
        if row["status"] != "complete":
            continue
        key = json.dumps(row["comparison"], sort_keys=True)
        group = groups.setdefault(key, dict(comparison=row["comparison"], cohorts=0, participants=0,
                                            task_satisfied=0, task_scored=0, pending_task_review=0, supported_infeasibility=0, tokens=0,
                                            communication=Counter(), matched_structure_cohorts=Counter()))
        group["cohorts"] += 1
        group["communication"][row["communication"]["status"]] += 1
        group["matched_structure_cohorts"].update({r["verdict"]["pattern"] for r in row["reviews"]
                                                   if r["status"] == "matched"})
        for actor in row["participants"].values():
            group["participants"] += 1
            if "task_satisfied" in actor["outcome"]:
                group["task_scored"] += 1
                group["task_satisfied"] += bool(actor["outcome"]["task_satisfied"])
            else:
                group["pending_task_review"] += 1
            group["supported_infeasibility"] += bool(actor["outcome"].get("infeasibility_supported"))
            group["tokens"] += actor["usage"]["tokens"]
    return list(groups.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path, help="Batch directory, sealed cohort, or .archive.json")
    parser.add_argument("--out", type=Path, help="Write report JSON (default: stdout)")
    parser.add_argument("--replay-tree", action="store_true", help="Re-score possible-Tree versions and supplemental probes in Docker")
    parser.add_argument("--diagnose-channels", action="store_true",
                        help="Locate access, writing and peer receipt in both conditions using bound process and service traces")
    args = parser.parse_args()
    if args.out and args.out.exists():
        try:
            existing = read(args.out)
        except (OSError, ValueError):
            existing = None
        if not isinstance(existing, dict) or existing.get("schema") != "swarmform-analysis-v1":
            parser.error("Output already exists and is not a SwarmForm analysis report")
    rows, seen = [], set()
    reviews = published_reviews() if args.diagnose_channels else {}
    for source in args.sources:
        try:
            listed = list(attempts(source.resolve()))
        except (OSError, ValueError, KeyError) as error:
            parser.error(str(error))
        for case, indexed, prior, label in listed:
            if args.out and args.out.resolve().is_relative_to(case.resolve()):
                parser.error("Choose an output outside the cohort evidence directory")
            try:
                if indexed.get("status") == "running" and not (case / "evidence-manifest.json").is_file():
                    result = dict(status="running")
                elif indexed.get("status") == "incomplete" and case.is_dir() and not (case / "evidence-manifest.json").exists():
                    result = dict(status="unsealed", reason=indexed.get("retry_reason"))
                else:
                    with cohort_directory(case) as directory:
                        result = analyze_case(directory, indexed, args.replay_tree, args.diagnose_channels)
                        if "channel_breakpoint" in result:
                            attach_review(result, reviews)
            except (OSError, ValueError, KeyError, RuntimeError, tarfile.TarError) as error:
                result = dict(status="invalid_evidence", reason=str(error))
            identity = result.get("evidence_manifest_sha256", case)
            if identity in seen:
                continue
            seen.add(identity)
            rows.append(dict(case=label, source=str(source), prior_attempts=prior, **result))
    result = dict(schema="swarmform-analysis-v1", status_counts=dict(Counter(r["status"] for r in rows)),
                  cohorts=rows, comparisons=summarize(rows))
    if args.out:
        atomic_json(args.out, result)
    else:
        json.dump(result, sys.stdout, indent=2)
        print()
    return int(any(r["status"] == "invalid_evidence" or "tree_replay_error" in r for r in rows))


if __name__ == "__main__":
    sys.exit(main())
