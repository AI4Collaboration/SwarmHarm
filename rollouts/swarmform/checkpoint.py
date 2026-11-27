"""Register the continuous work policy and shared cohort deadline."""

COHORT_SECONDS = 1800


def cohort_registration(args):
    return {"work_policy": "continuous",
            "cohort_deadline_seconds": getattr(args, "cohort_seconds", None) or COHORT_SECONDS,
            "online_structure_review": False}
