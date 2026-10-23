"""Optional researcher-defined record visibility; absent in the canonical study."""

from copy import deepcopy


def validate(spec, plan):
    """Validate an arbitrary static directed graph over stable logical agent IDs."""
    if spec is None:
        return None
    if not isinstance(spec, dict) or spec.get("kind") != "directed_graph":
        raise ValueError("topology kind must be directed_graph")
    logical_ids = {item["logical_id"] for item in plan.values()}
    if len(logical_ids) != len(plan):
        raise ValueError("logical agent IDs must be unique")
    if not isinstance(spec.get("self_visibility", True), bool):
        raise ValueError("self_visibility must be boolean")
    if spec.get("service_visibility", "all") not in {"all", "none"}:
        raise ValueError("service_visibility must be all or none")
    edges = spec.get("edges")
    if not isinstance(edges, list):
        raise ValueError("topology edges must be a list")
    normalized = []
    for edge in edges:
        if not isinstance(edge, list) or len(edge) != 2:
            raise ValueError("each topology edge must be [source, reader]")
        source, reader = edge
        if source not in logical_ids or reader not in logical_ids:
            raise ValueError("topology edge references an unknown logical agent ID")
        normalized.append((source, reader))
    if len(set(normalized)) != len(normalized):
        raise ValueError("topology edges must be unique")
    return {
        "kind": "directed_graph",
        "edge_semantics": "record_author_to_reader",
        "self_visibility": spec.get("self_visibility", True),
        "service_visibility": spec.get("service_visibility", "all"),
        "edges": [list(edge) for edge in normalized],
    }


class Visibility:
    def __init__(self, spec, plan):
        self.plan = deepcopy(plan)
        self.spec = validate(spec, plan)
        self.logical = {
            actor: item["logical_id"] for actor, item in self.plan.items()
        }
        self.edges = {
            tuple(edge) for edge in self.spec["edges"]
        } if self.spec is not None else set()

    def can_read(self, reader, record):
        if self.spec is None:
            return True
        source = record.get("source_actor", record.get("author"))
        if source == reader:
            return self.spec["self_visibility"]
        if source not in self.logical:
            return self.spec["service_visibility"] == "all"
        return (self.logical[source], self.logical[reader]) in self.edges

    def files_for(self, reader, shared):
        return {
            path: deepcopy(record)
            for path, record in shared.items()
            if self.can_read(reader, record)
        }
