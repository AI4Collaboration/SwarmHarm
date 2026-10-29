"""Compile one unstructured population with overlapping execution."""

import secrets

import domain_runtime


MAX_POPULATION = 128
CUE_CONDITIONS = (
    "agent_initiated_activity",
    "ambient_activity",
    "surfaced_activity",
    "workflow_affordance",
    "related_record_affordance",
    "context_contribution_affordance",
    "activity_notification_affordance",
    "triage_routing_affordance",
    "matched_case_assignment_affordance",
)
DEFAULT_CUE_CONDITION = "agent_initiated_activity"


def compile_plan(
    population=4,
    provider="sol",
    id_factory=None,
    business_pressure=None,
    cue_condition=DEFAULT_CUE_CONDITION,
    scenario=domain_runtime.SHARED_FIXTURE,
):
    if type(population) is not int or not 4 <= population <= MAX_POPULATION:
        raise ValueError(f"population must be between 4 and {MAX_POPULATION}")
    if cue_condition not in CUE_CONDITIONS:
        raise ValueError(f"cue condition must be one of {CUE_CONDITIONS}")
    # Offline component checks also use the shared implementation fixtures.
    # The public runner validates its four live choices before reaching here.
    scenario = domain_runtime.implementation(scenario)
    scenario_mechanics = domain_runtime.mechanics(scenario)
    make_id = id_factory or (lambda: "job-" + secrets.token_hex(6))
    pressure = business_pressure or scenario_mechanics.business_pressure(
        "2030-01-01T17:00:00+00:00"
    )
    fixtures = getattr(scenario_mechanics, "fixtures", None)
    if fixtures is None:
        fixtures = scenario_mechanics.formation_fixtures
    rows = fixtures(population)
    plan = {}
    for batch in rows:
        cases = batch.get("reviews", batch.get("checks"))
        case_ids = [case.get("review_id", case.get("check_id")) for case in cases]
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
            "review_ids": case_ids,
            "scenario": scenario,
            "domain": domain_runtime.public_domain(scenario),
            "business_pressure": pressure.copy(),
            # Registered environment factor: controls case creation,
            # record visibility and presentation after discovery.
            "cue_condition": cue_condition,
        }
    return {"natural": plan}, rows


def simultaneous_admissions(plan, limit):
    """Return one unordered activation cohort or reject a staged run."""
    if limit != len(plan):
        raise ValueError("canonical formation requires every context active together")
    return set(plan)
