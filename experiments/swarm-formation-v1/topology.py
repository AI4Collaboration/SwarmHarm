"""Compile a small researcher-facing visibility specification into a hidden runtime plan."""

import json
from pathlib import Path
import secrets

import mechanics


MAX_POPULATION = 128


def default_spec(population=3, preset="ring"):
    return {"population": population, "topology": {"preset": preset}}


def load_spec(path=None, *, population=3, preset="ring"):
    value = json.loads(Path(path).read_text()) if path else default_spec(population, preset)
    validate_spec(value)
    return value


def logical_id(index):
    return f"agent-{index + 1:06d}"


def adjacency(spec):
    validate_spec(spec)
    count = spec["population"]
    preset = spec["topology"]["preset"]
    graph = {logical_id(index): set() for index in range(count)}
    if preset == "all_to_all":
        for left in graph:
            graph[left] = set(graph) - {left}
    elif preset == "ring":
        for index in range(count):
            left, right = logical_id(index), logical_id((index + 1) % count)
            graph[left].add(right)
            graph[right].add(left)
    else:
        for left_index, right_index in spec["topology"]["links"]:
            left, right = logical_id(left_index), logical_id(right_index)
            graph[left].add(right)
            graph[right].add(left)
    return graph


def validate_spec(spec):
    if not isinstance(spec, dict) or set(spec) != {"population", "topology"}:
        raise ValueError("spec must contain population and topology")
    count = spec["population"]
    if type(count) is not int or not 2 <= count <= MAX_POPULATION:
        raise ValueError(f"population must be an integer between 2 and {MAX_POPULATION}")
    topology = spec["topology"]
    if not isinstance(topology, dict) or topology.get("preset") not in {
        "all_to_all",
        "ring",
        "explicit",
    }:
        raise ValueError("topology preset must be all_to_all, ring or explicit")
    if topology["preset"] != "explicit":
        if set(topology) != {"preset"}:
            raise ValueError("preset topology accepts no links")
        return
    if set(topology) != {"preset", "links"} or not isinstance(topology["links"], list):
        raise ValueError("explicit topology requires links")
    seen = set()
    degree = [0] * count
    for link in topology["links"]:
        if not isinstance(link, list) or len(link) != 2 or any(type(index) is not int for index in link):
            raise ValueError("each link must contain two integer indices")
        left, right = link
        if not (0 <= left < count and 0 <= right < count) or left == right:
            raise ValueError("link index is out of range or self-referential")
        edge = tuple(sorted((left, right)))
        if edge in seen:
            raise ValueError("duplicate link")
        seen.add(edge)
        degree[left] += 1
        degree[right] += 1
    if any(value == 0 for value in degree):
        raise ValueError("every logical agent needs at least one visible neighbor")


def resource_locations(graph, replicas=2):
    """Place each missing resource in a small reachable pool without assigning a responder."""
    result = {}
    for index, source in enumerate(graph):
        candidates = sorted(graph[source])
        start = index % len(candidates)
        ordered = candidates[start:] + candidates[:start]
        result[source] = ordered[: min(replicas, len(ordered))]
    return result


def all_to_all_resource_locations(population, replicas=2):
    """Select a bounded resource pool without materializing every visibility edge."""
    result = {}
    for index in range(population):
        result[logical_id(index)] = [
            logical_id((index + offset) % population)
            for offset in range(1, min(replicas, population - 1) + 1)
        ]
    return result


def compile_plan(spec, provider, id_factory=None):
    """Randomize runtime identities without changing the researcher visibility graph."""
    validate_spec(spec)
    all_visible = spec["topology"]["preset"] == "all_to_all"
    graph = None if all_visible else adjacency(spec)
    locations = (
        all_to_all_resource_locations(spec["population"])
        if all_visible
        else resource_locations(graph)
    )
    make_id = id_factory or (lambda: "worker-" + secrets.token_hex(6))
    actor_for = {logical_id(index): make_id() for index in range(spec["population"])}
    cases = mechanics.fixtures(spec["population"])
    case_for = {case["logical_id"]: case for case in cases}
    resources_at = {logical: [] for logical in actor_for}
    for requester, available_at in locations.items():
        for location in available_at:
            resources_at[location].append(requester)
    plan = {}
    for index in range(spec["population"]):
        logical = logical_id(index)
        case = case_for[logical]
        provided = [
            case["request_id"] + "-requisition.json",
            case["request_id"] + "-budget.json",
            case["lines"][0]["vendor"] + "-quote.json",
        ]
        for requester in resources_at[logical]:
            other = case_for[requester]
            provided.append(other["lines"][1]["vendor"] + "-quote.json")
        actor = actor_for[logical]
        plan[actor] = {
            "provider": provider,
            "arrival": index,
            "wave": 0,
            "population": spec["population"],
            "logical_id": logical,
            "request_id": case["request_id"],
            "provided": sorted(set(provided)),
            "visibility": (
                {"preset": "all_to_all"}
                if all_visible
                else {"preset": "explicit", "actors": sorted(actor_for[value] for value in graph[logical])}
            ),
            "missing_document": case["lines"][1]["vendor"] + "-quote.json",
        }
    return {"natural": plan}, cases, {
        "actor_for_logical_id": actor_for,
        "resource_locations": {
            actor_for[key]: [actor_for[value] for value in available_at]
            for key, available_at in locations.items()
        },
        "logical_visibility": (
            {"preset": "all_to_all"}
            if all_visible
            else {"preset": "explicit", "adjacency": {key: sorted(value) for key, value in graph.items()}}
        ),
    }
