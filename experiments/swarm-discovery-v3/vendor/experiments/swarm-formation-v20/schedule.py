"""Compile one unstructured population with overlapping execution."""

import secrets

import mechanics


MAX_POPULATION = 128


def compile_plan(population=4, provider="deepseek", id_factory=None, business_pressure=None):
    if type(population) is not int or not 4 <= population <= MAX_POPULATION:
        raise ValueError(f"population must be between 4 and {MAX_POPULATION}")
    make_id = id_factory or (lambda: "job-" + secrets.token_hex(6))
    pressure = business_pressure or mechanics.business_pressure("2030-01-01T17:00:00+00:00")
    rows = mechanics.fixtures(population)
    plan = {}
    for batch in rows:
        actor = make_id()
        plan[actor] = {
            "provider": provider,
            # Every subject belongs to one activation cohort.  This is not an
            # arrival rank: the collector releases the whole cohort through a
            # start barrier before any first model request can run.
            "start_group": 0,
            "population": population,
            "logical_id": batch["logical_id"],
            "batch_id": batch["batch_id"],
            "review_ids": [case["review_id"] for case in batch["reviews"]],
            "business_pressure": pressure.copy(),
        }
    return {"natural": plan}, rows


def simultaneous_admissions(plan, limit):
    """Return one unordered activation cohort or reject a staged run."""
    if limit != len(plan):
        raise ValueError("canonical formation requires every context active together")
    return set(plan)
