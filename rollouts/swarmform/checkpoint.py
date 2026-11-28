"""Register the continuous work policy and shared cohort deadline."""

COHORT_SECONDS = 600
LARGE_COHORT_SECONDS = 1200
SPECIAL_CASE_COHORT_SECONDS = 1800


def default_cohort_seconds(task=None, population=None):
    if task == "navier-stokes-3d-possible":
        return SPECIAL_CASE_COHORT_SECONDS
    if isinstance(population, int) and population >= 16:
        return LARGE_COHORT_SECONDS
    return COHORT_SECONDS


def cohort_registration(args, task=None, population=None):
    selected = task if task is not None else getattr(args, "task", None)
    pop = population if population is not None else getattr(args, "population", None)
    return {"work_policy": "continuous",
            "cohort_deadline_seconds": getattr(args, "cohort_seconds", None) or default_cohort_seconds(selected, pop),
            "online_structure_review": False}
