"""Compile hidden arrival timing for one shared, unstructured population."""

import secrets

import mechanics


MAX_POPULATION = 128


def compile_plan(population=3, provider="deepseek", id_factory=None):
    if type(population) is not int or not 3 <= population <= MAX_POPULATION:
        raise ValueError(f"population must be between 3 and {MAX_POPULATION}")
    make_id = id_factory or (lambda: "worker-" + secrets.token_hex(6))
    rows = mechanics.fixtures(population)
    plan = {}
    for arrival, case in enumerate(rows):
        actor = make_id()
        plan[actor] = {
            "provider": provider,
            "arrival": arrival,
            "wave": case["wave"],
            "population": population,
            "logical_id": case["logical_id"],
            "review_id": case["review_id"],
        }
    if {item["wave"] for item in plan.values()} != {0, 1, 2}:
        raise AssertionError("each formation milestone needs an arrival period")
    return {"natural": plan}, rows


def next_admissions(plan, pending, active, limit):
    """Fill free slots without crossing an unfinished arrival-period boundary."""
    if not pending or len(active) >= limit:
        return []
    wave = plan[active[0]]["wave"] if active else plan[pending[0]]["wave"]
    if any(plan[actor]["wave"] != wave for actor in active):
        raise AssertionError("active agents must belong to one arrival period")
    available = limit - len(active)
    admitted = []
    for actor in pending:
        if plan[actor]["wave"] != wave or len(admitted) >= available:
            break
        admitted.append(actor)
    return admitted
