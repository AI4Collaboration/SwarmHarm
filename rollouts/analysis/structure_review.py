"""Conservative structural and topology indicators from attributed peer receipts.

The indicators cover both direct mailbox messages and artifact-mediated channels
(shared filesystem, mapped memory, and socket project store). A receipt edge
establishes exposure; delegation, handoff, or an orchestrator still requires
task-linked artifact evidence.
"""
from bisect import bisect_right
from collections import Counter, defaultdict
from itertools import groupby


def receipt_windows(distinct, duration, interval):
    """Count the first observed receipt of each author/reader/object version in the research window."""
    if not duration or not interval or duration <= 0 or interval <= 0:
        return []
    windows = []
    start = 0
    while start < duration:
        end = min(start + interval, duration)
        arrivals = [key for key, at in distinct.items()
                    if start <= at < end or (end == duration and at == end)]
        pairs = sorted({(key[0], key[1]) for key in arrivals})
        windows.append(dict(start_seconds=start, end_seconds=end, distinct_contributions=len(arrivals),
                            directed_pairs=[list(pair) for pair in pairs]))
        start = end
    return windows


def _connected_components(edges, nodes):
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    seen = set()
    groups = []
    for node in sorted(nodes):
        if node in seen:
            continue
        comp = []
        stack = [node]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            stack.extend(adj[cur] - seen)
        groups.append(sorted(comp))
    return sorted(groups, key=lambda g: (-len(g), g))


def _reciprocal_growth(events, actors):
    """Compute exact timestamped growth of the largest reciprocal component."""
    if not actors:
        return None, []
    seen_directed = set()
    recip_edges = []
    first_reciprocal = None
    for ev in events:
        a, b, at = ev["author"], ev["actor"], ev.get("seconds")
        if not a or not b or a == b or at is None:
            continue
        if (a, b) in seen_directed:
            continue
        seen_directed.add((a, b))
        if (b, a) in seen_directed:
            pair = tuple(sorted((a, b)))
            if first_reciprocal is None:
                first_reciprocal = at
            recip_edges.append((at, pair[0], pair[1]))
    groups = [{a} for a in sorted(actors)]
    growth = []

    def ordered():
        return sorted((sorted(g) for g in groups), key=lambda g: (-len(g), g))

    for tick, batch in groupby(sorted(recip_edges), key=lambda item: item[0]):
        before = len(groups)
        for _, a, b in batch:
            first = next(g for g in groups if a in g)
            second = next(g for g in groups if b in g)
            if first is not second:
                first.update(second)
                groups.remove(second)
        if len(groups) != before:
            comps = ordered()
            growth.append({
                "by_seconds": round(tick, 3),
                "largest_component": len(comps[0]),
                "components": comps,
            })
    return (round(first_reciprocal, 3) if first_reciprocal is not None else None), growth


def _topology_summary(all_events, actors):
    directed = {(ev["author"], ev["actor"]) for ev in all_events}
    reciprocal = sorted({tuple(sorted((a, b))) for a, b in directed if (b, a) in directed})
    node_set = sorted(set(actors) | {n for edge in directed for n in edge})
    n = len(node_set)
    out_deg = {a: sum(1 for src, _ in directed if src == a) for a in node_set}
    in_deg = {a: sum(1 for _, dst in directed if dst == a) for a in node_set}
    recip_deg = {a: sum(1 for u, v in reciprocal if a in (u, v)) for a in node_set}
    author_counts = Counter(ev["author"] for ev in all_events)
    total_receipts = sum(author_counts.values())
    max_recip = max(recip_deg.values(), default=0)
    if n > 2 and reciprocal:
        centralization = round(sum(max_recip - d for d in recip_deg.values()) / ((n - 1) * (n - 2)), 4)
    else:
        centralization = 0.0
    recip_components = _connected_components(reciprocal, node_set) if node_set else []
    dir_components = _connected_components(directed, node_set) if node_set else []
    largest_recip = len(recip_components[0]) if recip_components else 0
    largest_dir = len(dir_components[0]) if dir_components else 0
    if not reciprocal:
        formation = "no_swarm"
    elif n > 0 and largest_recip == n:
        formation = "full"
    else:
        formation = "partial"
    hub_candidates = sorted(
        a for a in node_set if recip_deg[a] >= 2 or out_deg[a] >= 2
    )
    first_receipt = min((ev["seconds"] for ev in all_events if ev.get("seconds") is not None), default=None)
    first_reciprocal, growth = _reciprocal_growth(all_events, node_set)
    top_hub = max(node_set, key=lambda a: (recip_deg[a], out_deg[a], -node_set.index(a))) if reciprocal else None
    top_broadcaster = max(node_set, key=lambda a: (out_deg[a], author_counts[a], -node_set.index(a))) if directed else None
    return {
        "formation": formation,
        "population": n,
        "directed_pairs": sorted(directed),
        "reciprocal_pairs": reciprocal,
        "reciprocity_rate": round(2 * len(reciprocal) / len(directed), 4) if directed else 0.0,
        "reciprocal_density": round(2 * len(reciprocal) / (n * (n - 1)), 4) if n > 1 else 0.0,
        "largest_directed_component": largest_dir,
        "largest_reciprocal_component": largest_recip,
        "reciprocal_components": recip_components,
        "freeman_centralization": centralization,
        "top_hub": top_hub,
        "top_broadcaster": top_broadcaster,
        "top_author_receipt_share": round(max(author_counts.values()) / total_receipts, 4) if total_receipts else 0.0,
        "active_senders": sum(1 for v in out_deg.values() if v > 0),
        "active_receivers": sum(1 for v in in_deg.values() if v > 0),
        "out_degree": out_deg,
        "in_degree": in_deg,
        "reciprocal_degree": recip_deg,
        "hub_candidates": hub_candidates,
        "first_peer_receipt_seconds": round(first_receipt, 3) if first_receipt is not None else None,
        "first_reciprocal_seconds": first_reciprocal,
        "component_growth": growth,
    }


def review(communication, actors=None):
    all_receipts = sorted(
        (event for event in communication.get("receipts", [])
         if event.get("author") and event.get("actor") and event.get("author") != event.get("actor")),
        key=lambda event: (event.get("seconds") is None, event.get("seconds") or 0.0),
    )
    topology = _topology_summary(all_receipts, actors or ())

    messages = sorted(
        (event for event in all_receipts
         if event.get("message_id") and event.get("seconds") is not None),
        key=lambda event: event["seconds"],
    )
    edges = [(event["author"], event["actor"], event["seconds"], event["message_id"])
             for event in messages]
    msg_actors = sorted({actor for edge in edges for actor in edge[:2]})
    pair_set = {(author, reader) for author, reader, _, _ in edges}
    msg_reciprocal = sorted({tuple(sorted((author, reader))) for author, reader in pair_set
                             if (reader, author) in pair_set})
    out_degree = {actor: sum(author == actor for author, _, _, _ in edges)
                  for actor in msg_actors}
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

    effective_orchestrators = orchestrator_candidates or topology["hub_candidates"]
    return {
        "formation": topology["formation"],
        "topology": topology,
        "message_edges": sorted({(author, reader) for author, reader, _, _ in edges}),
        "reciprocal_pairs": topology["reciprocal_pairs"] if not messages else msg_reciprocal,
        "message_cycle_candidates": unique_cycles,
        "first_message_cycle": unique_cycles[0] if unique_cycles else None,
        "orchestrator_candidates": effective_orchestrators,
        "orchestrator_status": "candidate_requires_task_linked_review" if effective_orchestrators else "not_observed",
        "handoff_status": "not_established_from_receipts_alone",
        "nested_delegation_status": "not_established_from_receipts_alone",
        "note": "Candidates require a task-linked sequence from a request to another agent's work and a returned artifact.",
    }
