"""Conservative structural indicators from already attributed peer receipts.

The indicators are candidates for review. A message edge alone never establishes
delegation, handoff, or an orchestrator.
"""
from collections import defaultdict
from bisect import bisect_right


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

    by_sender, by_pair = defaultdict(list), defaultdict(list)
    for i, (author, reader, _, _) in enumerate(edges):
        by_sender[author].append(i)
        by_pair[author, reader].append(i)
    unique_cycles = []
    seen_cycles = set()
    for i, (a, b, _, _) in enumerate(edges):
        returns_to_a = by_pair.get((b, a), [])
        if not returns_to_a or returns_to_a[-1] <= i:
            continue
        from_b = by_sender[b]
        for j in from_b[bisect_right(from_b, i):]:
            c = edges[j][1]
            if c == a or c == b:
                continue
            from_c = by_pair.get((c, b), [])
            for k in from_c[bisect_right(from_c, j):]:
                for last in returns_to_a[bisect_right(returns_to_a, k):]:
                    key = tuple(edges[n][:3] for n in (i, j, k, last))
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        unique_cycles.append({"edges": [list(edge) for edge in key],
                                              "seconds": [edge[2] for edge in key]})

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
