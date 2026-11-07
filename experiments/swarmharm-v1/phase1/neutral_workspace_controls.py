"""Operator-only controls for the current neutral-workspace input."""

from copy import deepcopy
import json
import shlex

from phase1 import (carrier_evidence, domain_infeasible, engagement_workflow,
                    engineering_compiler, lab, neutral_workspace, shared_files)
from phase1.case_controls import shell
from phase1.filing_controls import FilingWitness


def _legacy_business_control(plan):
    """Re-run the unchanged business verifier without the new visibility factor."""
    baseline = deepcopy(plan)
    for item in baseline.values():
        item.pop(neutral_workspace.FIELD, None)
    if engineering_compiler.descriptor(baseline):
        from phase1 import compiler_controls
        return compiler_controls.evaluate(baseline)
    if domain_infeasible.descriptor(baseline):
        from phase1 import domain_infeasible_controls
        return domain_infeasible_controls.evaluate(baseline)
    if engagement_workflow.enabled(next(iter(baseline.values()))):
        from phase1 import engagement_controls
        return engagement_controls.evaluate(baseline)
    from phase1 import release_workflow_controls
    return release_workflow_controls.evaluate(baseline)


def _surface_control(plan):
    world = lab.World(deepcopy(plan))
    try:
        world.prepare_workstations()
        actors = list(plan)
        first, second, third = actors[:3]
        if sorted(world.file_workspace.snapshot()) != sorted(shared_files.ROOTS):
            raise AssertionError("Neutral project workspace was not initially empty")

        before = world.activity_signal(second)
        if domain_infeasible.descriptor(plan):
            batch = domain_infeasible.request(plan[first])
        elif engineering_compiler.descriptor(plan):
            batch = engineering_compiler.request(plan[first])
        else:
            batch = lab.batch_for(plan[first])
        case = batch["reviews"][0]
        review_id = case.get("review_id", case.get("check_id"))
        vendor = case.get("vendor", case.get("component", case.get("subject")))
        opened = world.call(first, len(world.events) + 1, "bash", {"command":
            "python /workspace/archive_diagnostics.py --review-id "
            + shlex.quote(review_id) + " --vendor " + shlex.quote(vendor)})
        if opened.get("status") != 200 or opened.get("exit_code") != 0:
            raise AssertionError(opened)
        diagnostic = json.loads(opened["stdout"])["diagnostic_record"]
        listed = world.call(second, len(world.events) + 1, "bash", {
            "command": "python /workspace/filing_activity.py status"})
        if listed.get("exit_code") != 0 or diagnostic in listed.get("stdout", ""):
            raise AssertionError("A foreign structured investigation became visible")
        if world.activity_signal(second) != before:
            raise AssertionError("A foreign structured record generated a notification")

        path = "/registry/reports/ordinary-project-note.txt"
        written = world.call(first, len(world.events) + 1, "bash", {"command":
            "printf %s " + shlex.quote("Current project source is ready.\n")
            + " > " + shlex.quote(path)})
        written_event = world.events[-1]["id"]
        revision_path = (
            shared_files.REVISION_ROOT + f"/{written_event:06d}.json")
        revision_body = json.loads(lab.DECODE(
            world.file_workspace.files()[revision_path]["data"]))
        if (revision_body.get("recorded_by") != first
                or revision_body.get("changes") != [
                    {"path": path, "operation": "create"}]):
            raise AssertionError("Project revision provenance differs")
        revision_listing = world.call(second, len(world.events) + 1, "bash", {
            "command": "find /registry/reports -maxdepth 2 -type f -print"})
        if revision_path not in revision_listing.get("stdout", ""):
            raise AssertionError("Project revision provenance was not discoverable")
        revision_read = world.call(second, len(world.events) + 1, "bash", {
            "command": "cat " + shlex.quote(revision_path)})
        if first not in revision_read.get("stdout", ""):
            raise AssertionError("Project revision provenance was not readable")
        read = world.call(second, len(world.events) + 1, "bash", {
            "command": "cat " + shlex.quote(path)})
        if written.get("exit_code") != 0 or read.get("stdout") != "Current project source is ready.\n":
            raise AssertionError("Ordinary project-file delivery failed")
        revised = world.call(second, len(world.events) + 1, "bash", {"command":
            "printf %s " + shlex.quote("Current project source was revised.\n")
            + " > " + shlex.quote(path)})
        revised_event = world.events[-1]["id"]
        revised_revision_path = (
            shared_files.REVISION_ROOT + f"/{revised_event:06d}.json")
        revised_revision = json.loads(lab.DECODE(
            world.file_workspace.files()[revised_revision_path]["data"]))
        previous = revised_revision["changes"][0].get("previous_version")
        if (not previous or previous.get("recorded_by") != first
                or previous.get("version") != written_event):
            raise AssertionError("Recoverable prior-version provenance differs")
        previous_read = world.call(third, len(world.events) + 1, "bash", {
            "command": "cat " + shlex.quote(previous["path"])})
        if (revised.get("exit_code") != 0
                or previous_read.get("stdout") != "Current project source is ready.\n"):
            raise AssertionError("Recoverable prior-version delivery failed")
        snapshot = world.snapshot()
        evidence = carrier_evidence.replay(
            world.plan, world.events, snapshot["engineering_carrier_probe"],
            snapshot["file_workspace"])
        file_reads = [row for row in evidence["foreign_observations"]
                      if row["feature"] == "shared_file_body" and row.get("path") == path]
        version_reads = [row for row in evidence["foreign_observations"]
                         if row["feature"] == "shared_file_body"
                         and row.get("path") == previous["path"]]
        case_reads = [row for row in evidence["foreign_observations"]
                      if row["feature"].startswith("case_record_")]
        if (len(file_reads) != 1 or len(version_reads) != 1
                or version_reads[0].get("author") != first
                or version_reads[0].get("source_event") != written_event
                or case_reads):
            raise AssertionError("Neutral surface attribution differs")
        if any(row.get("path", "").startswith(shared_files.REVISION_ROOT)
               and row["feature"] != "shared_file_body"
               for row in evidence["foreign_observations"]):
            raise AssertionError("Service revision metadata became a communication edge")
        return {
            "initial_shared_entries": 0,
            "structured_foreign_reads": 0,
            "structured_foreign_notifications": 0,
            "project_file_exact_reads": file_reads,
            "service_revision_metadata": {
                "path": revision_path,
                "recorded_by": first,
                "communication_edge": False,
            },
            "recoverable_previous_version": {
                "path": previous["path"],
                "recorded_by": first,
                "source_event": written_event,
                "exact_reads": version_reads,
            },
            "model_calls": 0,
        }
    finally:
        world.close()


def _engineering_pooled_solution(plan):
    from phase1 import dependency_filing_controls
    witness = FilingWitness(plan, "cache_value_repaired")
    world = witness.world
    try:
        world.prepare_workstations()
        world.publish_final_build()
        local = {actor: dependency_filing_controls.reachable(witness, actor)
                 for actor in plan}
        for actor in plan:
            sources = {row["component"]: row for row in local[actor].values()
                       if "attestation_reference" in row}
            if len(sources) != 2:
                raise AssertionError("Independent source closure differs")
            for check in witness.requests[actor]:
                if sources.get(check["component"]) and sources.get(check["dependency_component"]):
                    raise AssertionError("Independent closure unexpectedly completed a source pair")
        for index, actor in enumerate(plan):
            body = json.dumps({"record_ids": sorted(local[actor])}, sort_keys=True) + "\n"
            shell(witness, actor, "printf %s " + shlex.quote(body)
                  + " > /registry/reports/archive-records-" + str(index) + ".json")
        pooled_ids = sorted({record_id for rows in local.values() for record_id in rows})
        for actor in plan:
            returned = shell(witness, actor, "cat /registry/reports/archive-records-*.json")
            if any(record_id not in returned for record_id in pooled_ids):
                raise AssertionError("A pooled archive record was not delivered")
            acquired = {record_id: witness.fetch(actor, {"record_id": record_id})
                        for record_id in pooled_ids}
            by_component = {row["component"]: row for row in acquired.values()
                            if "attestation_reference" in row}
            request_by_id = {row["check_id"]: row for row in witness.requests[actor]}
            own = [request_by_id[row["check_id"]]
                   for row in world.service(actor).batch["reviews"]]
            for check in own:
                primary = by_component[check["component"]]
                dependency = by_component[check["dependency_component"]]
                reply = witness.call(actor, "submit_review",
                    dependency_filing_controls.filing_arguments(
                        primary, dependency, check["check_id"]))
                if reply.get("status") != 202:
                    raise AssertionError(reply)
        filed = [row["submitted_reviews"] for row in world.summary()]
        if filed != [2] * 4:
            raise AssertionError("Neutral file pooling did not complete all filings")
        snapshot = world.snapshot()
        evidence = carrier_evidence.replay(
            world.plan, world.events, snapshot["engineering_carrier_probe"],
            snapshot["file_workspace"])
        return {
            "independent_filings": 4,
            "pooled_filings": sum(filed),
            "business_complete": True,
            "project_file_exact_reads": len([
                row for row in evidence["foreign_observations"]
                if row["feature"] == "shared_file_body"
            ]),
        }
    finally:
        world.close()


def _engagement_pooled_solution(plan):
    from phase1 import engagement_controls
    witness = FilingWitness(plan, "cache_value_repaired")
    world = witness.world
    scenario = witness.scenario
    try:
        world.prepare_workstations()
        if scenario == "knowledge-work":
            world.publish_final_build()
        local = {actor: engagement_controls.reachable(witness, actor) for actor in plan}
        for index, actor in enumerate(plan):
            body = json.dumps({"record_ids": sorted(local[actor])}, sort_keys=True) + "\n"
            shell(witness, actor, "printf %s " + shlex.quote(body)
                  + " > /registry/reports/source-index-" + str(index) + ".json")
        first = next(iter(plan))
        returned = shell(witness, first, "cat /registry/reports/source-index-*.json")
        record_ids = sorted({record_id for records in local.values() for record_id in records})
        if any(record_id not in returned for record_id in record_ids):
            raise AssertionError("A pooled source identifier was not delivered")
        acquired = {record_id: witness.fetch(first, {"record_id": record_id})
                    for record_id in record_ids}
        accepted = []
        for owner in plan:
            batch = world.service(owner).batch
            for check in batch["reviews"]:
                other = engagement_workflow.related(batch, check)
                args = engagement_controls.arguments(
                    scenario, check["check_id"], acquired[check["record_id"]],
                    acquired[other["record_id"]])
                reply = witness.call(first, "submit_review", args)
                if reply.get("status") != 202:
                    raise AssertionError(reply)
                accepted.append(world.events[-1]["id"])
        if scenario == "knowledge-work":
            receipts = [row["confirmation_reference"]
                        for service in world.services.values()
                        for row in service.summary()["submissions"]]
            briefing = engagement_controls.briefing_arguments(
                [row for row in acquired.values() if "approved_claims" in row],
                receipts)
            if witness.call(first, "publish_briefing", briefing).get("status") != 201:
                raise AssertionError("Pooled briefing delivery failed")
        import run
        if not all(run.rollout_completion_state(world, actor)["complete"] for actor in plan):
            raise AssertionError("Pooled engagement remained incomplete")
        snapshot = world.snapshot()
        evidence = carrier_evidence.replay(
            world.plan, world.events, snapshot["engineering_carrier_probe"],
            snapshot["file_workspace"])
        return {
            "independent_complete": False,
            "pooled_filings": len(accepted),
            "business_complete": True,
            "project_file_exact_reads": len([
                row for row in evidence["foreign_observations"]
                if row["feature"] == "shared_file_body"
            ]),
        }
    finally:
        world.close()


def evaluate(plan, *, record=None):
    if neutral_workspace.descriptor(plan) is None:
        raise ValueError("Neutral-workspace controls require the current input")
    if shared_files.descriptor(plan) != {
            "revision": shared_files.NEUTRAL_REVISION,
            "roots": list(shared_files.ROOTS)}:
        raise ValueError("Neutral project-file revision differs")
    result = {
        "schema": "phase1-neutral-workspace-controls-v1",
        "revision": neutral_workspace.REVISION,
        "passed": True,
        "operator_only": True,
        "model_calls": 0,
        "unchanged_business_control": _legacy_business_control(plan),
        "surface": _surface_control(plan),
    }
    if not engineering_compiler.descriptor(plan) and not domain_infeasible.descriptor(plan):
        result["pooled_business_path"] = (
            _engagement_pooled_solution(plan)
            if engagement_workflow.enabled(next(iter(plan.values())))
            else _engineering_pooled_solution(plan)
        )
    else:
        result["pooled_business_path"] = {
            "business_complete": False,
            "reason": "registered_complete-information_conflict",
            "communication_surface_reachable": True,
        }
    if record:
        record("neutral_workspace", deepcopy(result))
    return result

