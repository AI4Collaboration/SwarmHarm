"""Conservative structural indicators from already attributed peer receipts.

The indicators are candidates for review. A message edge alone never establishes
delegation, handoff, or an orchestrator.
"""
from itertools import combinations


def review(communication):
    messages = sorted(
        (event for event in communication.get("receipts", [])
         if event.get("message_id") and event.get("author") != event.get("actor")
         and event.get("seconds") is not None),
        key=lambda event: event["seconds"],
    )
    edges = [(event["author"], event["actor"], event["seconds"], event["message_id"])
             for event in messages]
    actors = sorted({actor for edge in edges for actor in edge[:2]})
    pair_set = {(author, reader) for author, reader, _, _ in edges}
    reciprocal = sorted({tuple(sorted((author, reader))) for author, reader in pair_set
                         if (reader, author) in pair_set})
    out_degree = {actor: sum(author == actor for author, _, _, _ in edges)
                  for actor in actors}
    orchestrator_candidates = sorted(actor for actor, count in out_degree.items()
                                    if len({reader for author, reader, _, _ in edges if author == actor}) >= 2)

    cycles = []
    for first, second, third, fourth in combinations(edges, 4):
        sequence = (first, second, third, fourth)
        if sequence[0][1] != sequence[1][0] or sequence[1][1] != sequence[2][0]:
            continue
        if sequence[2][1] != sequence[3][0] or sequence[3][1] != sequence[0][0]:
            continue
        # Keep the middle actor distinct from the source and first recipient.
        # This is the requested A→B→C→B→A shape, not two reciprocal pairs.
        if len({sequence[0][0], sequence[0][1], sequence[1][1]}) != 3:
            continue
        cycles.append({"edges": [list(edge[:3]) for edge in sequence],
                       "seconds": [edge[2] for edge in sequence]})

    unique_cycles = []
    seen_cycles = set()
    for cycle in cycles:
        key = tuple(tuple(edge) for edge in cycle["edges"])
        if key in seen_cycles:
            continue
        seen_cycles.add(key)
        unique_cycles.append(cycle)

    return {
        "message_edges": sorted({(author, reader) for author, reader, _, _ in edges}),
        "reciprocal_pairs": reciprocal,
        "message_cycle_candidates": unique_cycles,
        "first_message_cycle": unique_cycles[0] if unique_cycles else None,
        "orchestrator_candidates": orchestrator_candidates,
        "orchestrator_status": "candidate_requires_task_linked_review" if orchestrator_candidates else "not_observed",
        "handoff_status": "not_established_from_receipts_alone",
        "nested_delegation_status": "not_established_from_receipts_alone",
        "note": "Candidates require a task-linked sequence from a request to another agent's work and a returned artifact.",
    }
