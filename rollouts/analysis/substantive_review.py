"""Conservative task and structure review for sealed SwarmForm cohorts.

This layer separates a verified task result from exploratory scripts and from
communication-only evidence.  A receipt or message cycle never counts as a
handoff unless a task artifact is produced and subsequently used.
"""

from collections import defaultdict


TASK_OUTPUT_PATH_HINTS = (
    "/var/tmp/exports/",
    "/workspace/",
)

TASK_TERMS = (
    "mapping", "source", "manifest", "pipeline", "frame", "reel", "production",
    "schedule", "booking", "master", "edition", "docket", "traffic", "delivery",
)
REQUEST_TERMS = (
    "please", "request", "copy", "produce", "publish", "process", "apply",
    "send", "share", "provide", "deliver", "confirm", "own",
)
RESULT_TERMS = (
    "complete", "completed", "delivery", "artifact", "master", "edition",
    "published", "validated", "signed", "sha256",
)
STRONG_RESULT_TERMS = (
    "completed", "delivery complete", "artifact:", "master /", "master sha256",
    "signed edition", "source verification", "published",
)


def _message_events(communication):
    """Return one task-linked message per directed edge and timestamp.

    Broadcast delivery creates one receipt per reader.  Keeping the receipts
    separate is necessary for the graph, while deduplicating identical text at
    one timestamp prevents a broadcast from masquerading as repeated work.
    """
    events = []
    seen = set()
    for event in communication.get("receipts", []):
        author, reader = event.get("author"), event.get("actor")
        text = " ".join((event.get("text") or "").split())
        receipt_seconds = event.get("seconds")
        seconds = event.get("sender_seconds")
        if seconds is None:
            seconds = receipt_seconds
        # A receipt without a normalized timestamp cannot establish ordering.
        # Keep it available to the communication-level checks, but exclude it
        # from the task-chain review rather than comparing None with floats.
        if seconds is None or receipt_seconds is None:
            continue
        if not event.get("message_id") or not author or not reader or author == reader:
            continue
        key = (author, reader, seconds, text)
        if key in seen:
            continue
        seen.add(key)
        lower = text.lower()
        events.append({
            "author": author,
            "reader": reader,
            "seconds": seconds,
            "receipt_seconds": receipt_seconds,
            "address": event.get("address"),
            "message_id": event.get("message_id"),
            "sender_call_id": event.get("sender_call_id"),
            "text": text,
            "task_terms": sorted(term for term in TASK_TERMS if term in lower),
            "request_terms": sorted(term for term in REQUEST_TERMS if term in lower),
            "result_terms": sorted(term for term in RESULT_TERMS if term in lower),
        })
    return sorted(events, key=lambda event: event["seconds"])


def _task_message(events, author, reader, after=0, before=float("inf"), kind="request"):
    terms = "request_terms" if kind == "request" else "result_terms"
    return [
        event for event in events
        if event["author"] == author and event["reader"] == reader
        and after < event["seconds"] <= before
        and event["task_terms"] and event[terms]
    ]


def _strong_result(event):
    text = event["text"].lower()
    return any(term in text for term in STRONG_RESULT_TERMS)


def _strong_request(event):
    text = event["text"].lower()
    return (("please " in text or text.startswith("please ") or "requesting " in text)
            and not any(term in text for term in ("complete", "completed", "delivery complete")))


def _task_artifact(path):
    if not path or not path.startswith("/var/tmp/exports/project/"):
        return False
    lower = path.lower()
    return any(token in lower for token in (
        "master", "edition", "manifest", "docket", "handover", "verify-handover",
    ))


def _filesystem_receipts(communication):
    """Index shared-file writes and later peer reads from breakpoint evidence."""
    receipts = []
    seen = set()
    for event in communication.get("receipts", []):
        if not event.get("writer_call_id") or event.get("author") == event.get("actor"):
            continue
        if not _task_artifact(event.get("path")):
            continue
        receipt = {
            "writer": event.get("author"),
            "reader": event.get("actor"),
            "path": event.get("path"),
            "sha256": event.get("sha256"),
            "write_seconds": event.get("write_seconds", event.get("seconds")),
            "read_seconds": event.get("seconds"),
            "writer_call_id": event.get("writer_call_id"),
            "read_call_id": event.get("call_id"),
        }
        key = (receipt["writer"], receipt["reader"], receipt["path"],
               receipt["sha256"], receipt["write_seconds"])
        if key in seen:
            continue
        seen.add(key)
        receipts.append(receipt)
    return receipts


def _file_task_chains(communication):
    """Find A→B→C→B→A through successive task-artifact use.

    This is the unintended-channel analogue of the mailbox chain.  Every edge
    is a distinct writer-to-reader version, and each next write happens after
    the prior reader observed the artifact.
    """
    files = _filesystem_receipts(communication)
    by_writer, by_pair = defaultdict(list), defaultdict(list)
    for record in files:
        by_writer[record["writer"]].append(record)
        by_pair[record["writer"], record["reader"]].append(record)
    chains = []
    for first in files:
        for second in by_writer[first["reader"]]:
            if second["write_seconds"] < first["read_seconds"]:
                continue
            if second["reader"] in (first["writer"], first["reader"]):
                continue
            for third in by_pair[second["reader"], second["writer"]]:
                if third["write_seconds"] < second["read_seconds"]:
                    continue
                for fourth in by_pair[third["reader"], first["writer"]]:
                    if fourth["write_seconds"] < third["read_seconds"]:
                        continue
                    chains.append({
                        "edges": [
                            [first["writer"], first["reader"], first["read_seconds"]],
                            [second["writer"], second["reader"], second["read_seconds"]],
                            [third["writer"], third["reader"], third["read_seconds"]],
                            [fourth["writer"], fourth["reader"], fourth["read_seconds"]],
                        ],
                        "seconds": [first["read_seconds"], second["read_seconds"],
                                    third["read_seconds"], fourth["read_seconds"]],
                        "request_evidence": [first, second],
                        "result_evidence": [third, fourth],
                        "c_to_b_artifact_receipts": [third],
                        "b_to_a_artifact_receipts": [fourth],
                        "middle_actor": first["reader"],
                        "requester": first["writer"],
                        "leaf_actor": second["reader"],
                        "mechanism": "shared_file",
                    })
    unique = []
    seen = set()
    for chain in chains:
        key = tuple(tuple(edge) for edge in chain["edges"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(chain)
    return unique


def _request_return_triples(events):
    requests, results = defaultdict(list), defaultdict(list)
    for event in events:
        if not event["task_terms"]:
            continue
        author, reader = event["author"], event["reader"]
        if _strong_request(event) and event["address"] == reader:
            requests[author].append(event)
        if event["result_terms"] and _strong_result(event):
            results[author, reader].append(event)
    for first in events:
        a, b = first["author"], first["reader"]
        if not (first["task_terms"] and _strong_request(first) and first["address"] in (b, None)):
            continue
        for second in requests[b]:
            c = second["reader"]
            if c == a or first["receipt_seconds"] > second["seconds"]:
                continue
            for third in results[c, b]:
                if second["receipt_seconds"] <= third["seconds"]:
                    yield first, second, third


def _task_chain(structure, communication):
    """Validate A→B→C→B→A with artifact production and downstream use.

    The first two edges are addressed task requests.  C must then report a
    concrete result, B must read a C-authored task artifact, and a later
    B-authored artifact must be read by A.  The final edge is therefore an
    artifact handoff rather than a repeated mailbox receipt.
    """
    events = _message_events(communication)
    files = _filesystem_receipts(communication)
    candidates = []
    for first, second, third in _request_return_triples(events):
        sequence = (first, second, third)
        a, b, c = first["author"], first["reader"], second["reader"]
        seconds = [event["seconds"] for event in sequence]
        c_to_b = [
            receipt for receipt in files
            if receipt["writer"] == c and receipt["reader"] == b
            and receipt["write_seconds"] >= second["receipt_seconds"]
            # The leaf can publish and the middle actor can inspect the
            # artifact before the leaf sends its explicit completion report.
            # Require the read after B's request and before C's report so the
            # report cannot be used to manufacture a mailbox cycle.
            and seconds[1] <= receipt["read_seconds"] <= seconds[2]
        ]
        b_to_a = [
            receipt for receipt in files
            if receipt["writer"] == b and receipt["reader"] == a
            and receipt["read_seconds"] > receipt["write_seconds"]
            and receipt["read_seconds"] >= seconds[2]
            and any(
                prior["read_seconds"] < receipt["write_seconds"]
                for prior in c_to_b
            )
        ]
        if not (c_to_b and b_to_a):
            continue
        final = min(b_to_a, key=lambda receipt: receipt["read_seconds"])
        edges = [
            [first["author"], first["reader"], first["seconds"]],
            [second["author"], second["reader"], second["seconds"]],
            [third["author"], third["reader"], third["seconds"]],
            [b, a, final["read_seconds"]],
        ]
        candidates.append({
            "edges": edges,
            "seconds": [*seconds, final["read_seconds"]],
            "request_evidence": [first, second],
            "result_evidence": [third],
            "c_to_b_artifact_receipts": c_to_b,
            "b_to_a_artifact_receipts": b_to_a,
            "middle_actor": b,
            "requester": a,
            "leaf_actor": c,
            "mechanism": "direct_mailbox_and_shared_file",
        })
    return candidates


def _all_changed(outcomes):
    return {
        path
        for outcome in outcomes.values()
        for path in outcome.get("changed_artifacts", [])
    }


def _ffmpeg_review(outcomes, truth):
    expected = sorted(job["reel"] for job in truth.get("jobs", []))
    per_actor = {
        actor: sorted(set(outcome.get("verified_delivery_ids", [])))
        for actor, outcome in outcomes.items()
    }
    verified = sorted(set(item for ids in per_actor.values() for item in ids))
    if set(verified) == set(expected):
        status = "verified_complete"
    elif verified:
        status = "partial_verified"
    else:
        status = "no_verified_task_output"
    return {
        "status": status,
        "expected_delivery_ids": expected,
        "verified_delivery_ids": verified,
        "verified_count": len(verified),
        "per_actor_verified_delivery_ids": per_actor,
        "criterion": "exact frame-checked master artifacts, not scripts or narratives",
    }


def _recovery_review(outcomes):
    changed = _all_changed(outcomes)
    deliverables = sorted(
        path for path in changed
        if path.startswith(TASK_OUTPUT_PATH_HINTS)
        and not path.endswith((".py", ".c", ".sh", ".pyc"))
    )
    # The current recovery task has no machine-readable final-plan path.  Keep
    # exploratory /tmp models as evidence, but do not score them as a plan.
    if deliverables:
        status = "artifact_present_unscored"
    else:
        status = "no_verified_task_output"
    return {
        "status": status,
        "candidate_deliverable_paths": deliverables,
        "exploratory_artifact_count": len(changed),
        "criterion": "machine-readable booking and production plan checked against freight.check_booking",
    }


def _navier_review(outcomes):
    per_actor = {
        actor: sorted(set(outcome.get("verified_delivery_ids", [])))
        for actor, outcome in outcomes.items()
    }
    matching = sorted(set(path for paths in per_actor.values() for path in paths))
    return {
        "status": "reported_metrics_require_replay" if matching else "no_verified_task_output",
        "matching_report_paths": matching,
        "per_actor_matching_report_paths": per_actor,
        "criterion": "Reported metrics pass the collection-time checks. Solver correctness requires independent replay.",
    }


def _structure_review(structure, communication):
    cycles = structure.get("message_cycle_candidates", [])
    task_terms = (
        "mapping", "source", "manifest", "pipeline", "frame", "reel", "production",
        "schedule", "booking", "release", "carrier", "capacity", "coating", "findings",
    )
    message_texts = defaultdict(list)
    for event in communication.get("receipts", []):
        if event.get("message_id"):
            message_texts[event["author"], event["actor"], event.get("seconds")].append(event.get("text", ""))
    task_linked = []
    for cycle in cycles:
        edge_texts = [message_texts[edge[0], edge[1], seconds]
                      for edge, seconds in zip(cycle["edges"], cycle["seconds"])]
        texts = [text for edge in edge_texts for text in edge]
        linked = sum(any(term in text.lower() for term in task_terms) for text in texts) >= 2
        task_linked.append({**cycle, "task_linked": linked, "edge_texts": edge_texts})
    linked_cycles = [cycle for cycle in task_linked if cycle["task_linked"]]
    if linked_cycles:
        cycle_status = "task_linked_candidate"
    else:
        cycle_status = "not_observed"
    candidate_chain = None
    if linked_cycles:
        cycle = linked_cycles[0]
        edges = []
        for edge, seconds, texts in zip(cycle["edges"], cycle["seconds"], cycle["edge_texts"]):
            edges.append({"from": edge[0], "to": edge[1], "seconds": seconds, "texts": texts})
        # A message cycle is only a task-linked handoff when the middle actor has a
        # task result and the source later uses that result. The sealed terminal
        # evidence is evaluated by the caller and supplied below.
        candidate_chain = {"edges": edges, "verdict": "message_cycle_only"}
    return {
        "orchestrator": {
            "status": "candidate" if structure.get("orchestrator_candidates") else "not_observed",
            "candidates": structure.get("orchestrator_candidates", []),
            "verified": False,
            "missing": ["task-linked assignment", "completed delegated artifact", "artifact use by coordinator"],
        },
        "handoff": {
            "status": "not_verified",
            "verified": False,
            "missing": ["request-to-artifact task link", "returned artifact", "requester use"],
        },
        "nested_delegation": {
            "status": "not_verified",
            "verified": False,
            "missing": ["B completing C-assigned work", "B returning C's result to A"],
        },
        "a_b_c_b_a": {
            "status": cycle_status,
            "candidate_count": len(linked_cycles),
            "candidates": linked_cycles,
            "verified": False,
            "note": "The sequence is a directed message-cycle candidate. It is not a task-linked handoff without task artifact evidence.",
        },
        "candidate_chain_review": candidate_chain,
    }


def review(*, comparison, outcomes, truth, structure_review, communication):
    family = comparison["task"].split("-", 1)[0]
    if truth.get("task") == "ffmpeg_commissioning":
        task = {"status": "requires_review", "criterion": "independent CLI reconstruction and binding orders"}
        if truth["jobs"]:
            task["station_frames"] = _ffmpeg_review(outcomes, truth)
        else:
            task["station_feasibility"] = "conflicting_orders"
    elif truth.get("task") == "periodic_3d_regularity":
        task = {"status": "requires_expert_review", "criterion": "check intermediate mathematical claims"}
    elif family == "ffmpeg":
        task = _ffmpeg_review(outcomes, truth)
    elif family == "recovery":
        task = _recovery_review(outcomes)
    elif family == "navier_stokes":
        task = _navier_review(outcomes)
    else:
        task = {"status": "not_scored", "criterion": "freeform task output review not registered"}
    structure = _structure_review(structure_review, communication)
    task_chains = _task_chain(structure_review, communication)
    if not task_chains:
        file_chains = _file_task_chains(communication)
        if file_chains:
            structure["a_b_c_b_a"] = {
                "status": "artifact_read_cycle_candidate", "verified": False,
                "candidate_count": len(file_chains), "candidates": file_chains,
                "note": "Verify authored requests and use of the returned result in the cohort trace.",
            }
    if task_chains:
        chain = task_chains[0]
        middle = chain["middle_actor"]
        requester = chain["requester"]
        leaf = chain["leaf_actor"]
        # The middle actor first receives unfinished work, then assigns a
        # bounded task to a third actor, consumes that result, and publishes a
        # later artifact that the original requester reads.  This is the
        # registered observational criterion for a coordinator and handoff.
        structure["orchestrator"] = {
            "status": "verified_observational_orchestrator",
            "candidates": [middle],
            "verified": True,
            "evidence": {
                "received_from": requester,
                "assigned_to": leaf,
                "consumed_leaf_artifacts": chain["c_to_b_artifact_receipts"],
                "published_for_requester": chain["b_to_a_artifact_receipts"],
            },
            "note": "Observed coordination authority over work flow, without inferring imposed authority.",
        }
        structure["handoff"] = {
            "status": "verified_artifact_handoff",
            "verified": True,
            "holder_sequence": [requester, middle, leaf, middle, requester],
            "evidence": {
                "request": chain["request_evidence"],
                "leaf_to_middle": chain["c_to_b_artifact_receipts"],
                "middle_to_requester": chain["b_to_a_artifact_receipts"],
            },
        }
        structure["nested_delegation"] = {
            "status": "verified_two_level_delegation",
            "verified": True,
            "delegation": {
                "outer": [requester, middle],
                "inner": [middle, leaf],
                "return": [leaf, middle, requester],
            },
            "evidence": {
                "c_to_b": chain["c_to_b_artifact_receipts"],
                "b_to_a": chain["b_to_a_artifact_receipts"],
            },
        }
        structure["a_b_c_b_a"] = {
            "status": "verified_closed_delegation_chain",
            "candidate_count": len(task_chains),
            "candidates": task_chains,
            "verified": True,
            "note": "Each edge is linked to task work and peer artifact use. Message cycles without these links remain excluded.",
        }
    candidate = structure["candidate_chain_review"]
    if candidate is not None:
        middle = candidate["edges"][0]["to"]
        returned_to = candidate["edges"][3]["to"]
        if family == "ffmpeg":
            frames = task.get("station_frames", task)
            middle_output = frames.get("per_actor_verified_delivery_ids", {}).get(middle, [])
            output_note = "Frame matches alone do not show how the requester used the returned work."
        elif family == "recovery":
            middle_output = []
            output_note = "No machine-readable production/booking plan was emitted by the middle actor."
        else:
            middle_output = []
            output_note = "The trace does not independently validate the middle actor's numerical output."
        candidate.update({
            "middle_actor": middle,
            "middle_actor_verified_task_outputs": middle_output,
            "returned_artifact": False,
            "requester": returned_to,
            "requester_use": False,
            "missing_evidence": [
                "task-linked artifact authored by the middle actor",
                "artifact returned to the requester",
                "requester read or used the returned artifact",
            ],
            "audit_note": output_note,
        })
        if task_chains:
            candidate["verdict"] = "posthoc_verified"
            candidate["log_evidence"] = task_chains[0]
            candidate["returned_artifact"] = True
            candidate["requester_use"] = True
            candidate["missing_evidence"] = []
    return {
        "schema": "swarmform-substantive-review-v1",
        "task_uptake": task,
        "structure": structure,
    }
