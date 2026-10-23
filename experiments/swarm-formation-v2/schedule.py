"""Compile hidden arrival timing for one shared, unstructured population."""

import secrets

import mechanics


MAX_POPULATION = 128


def compile_plan(population=6, provider="deepseek", id_factory=None):
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
