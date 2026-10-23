"""Compile one unstructured population with overlapping execution."""

import secrets

import mechanics


MAX_POPULATION = 128


def compile_plan(population=4, provider="deepseek", id_factory=None, business_pressure=None):
    if type(population) is not int or not 4 <= population <= MAX_POPULATION:
        raise ValueError(f"population must be between 4 and {MAX_POPULATION}")
    make_id = id_factory or (lambda: "worker-" + secrets.token_hex(6))
    pressure = business_pressure or mechanics.business_pressure("2030-01-01T17:00:00+00:00")
    rows = mechanics.fixtures(population)
    plan = {}
    for arrival, case in enumerate(rows):
        actor = make_id()
        plan[actor] = {
            "provider": provider,
            "arrival": arrival,
            "population": population,
            "logical_id": case["logical_id"],
            "review_id": case["review_id"],
            "business_pressure": pressure.copy(),
        }
    return {"natural": plan}, rows


def next_admissions(plan, pending, active, limit):
    """Fill free execution slots without assigning roles or relationships."""
    if not pending or len(active) >= limit:
        return []
    available = limit - len(active)
    return pending[:available]
