"""Register the continuous work policy and shared cohort deadline."""

COHORT_SECONDS = 600
SPECIAL_CASE_COHORT_SECONDS = 1800


def default_cohort_seconds(task=None):
    return SPECIAL_CASE_COHORT_SECONDS if task == "navier-stokes-3d-possible" else COHORT_SECONDS


def cohort_registration(args, task=None):
    selected = task if task is not None else getattr(args, "task", None)
    return {"work_policy": "continuous",
            "cohort_deadline_seconds": getattr(args, "cohort_seconds", None) or default_cohort_seconds(selected),
            "online_structure_review": False}
