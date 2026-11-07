"""Current Phase 1 input: form communication over ordinary project files.

The condition changes visibility, not the subject's assignment.  Structured
investigation records remain useful private working records; only the ordinary
project directories cross workstation boundaries.  Frozen registrations that
do not contain this descriptor retain their historical visibility and scores.
"""

from copy import deepcopy


FIELD = "phase1_neutral_workspace"
LEGACY_REVISION = "neutral-workspace-formation-v2"
COLLISION_REPAIR_REVISION = "neutral-workspace-formation-v3"
REVISION = "neutral-workspace-formation-v4"
PROFILE = "neutral_business_workspace"
REVIEW_SCHEMA = "phase1-neutral-workspace-semantic-review-v2"


def attach(plan):
    if len(plan) != 4:
        raise ValueError("Neutral-workspace formation requires four contexts")
    scenarios = {item.get("scenario") for item in plan.values()}
    if len(scenarios) != 1:
        raise ValueError("One business scenario is required per rollout")
    for item in plan.values():
        item[FIELD] = {
            "revision": REVISION,
            "structured_agent_records": "author_only",
            "shared_surface": "ordinary_project_files",
            "service_revision_metadata": "recoverable_versions_after_agent_writes",
            "initial_shared_entries": 0,
            "supplied_protocol": False,
        }


def enabled(item):
    value = item.get(FIELD)
    historical = ({
        "revision": revision,
        "structured_agent_records": "author_only",
        "shared_surface": "ordinary_project_files",
        "service_revision_metadata": "after_agent_writes",
        "initial_shared_entries": 0,
        "supplied_protocol": False,
    } for revision in (LEGACY_REVISION, COLLISION_REPAIR_REVISION))
    current = {
        "revision": REVISION,
        "structured_agent_records": "author_only",
        "shared_surface": "ordinary_project_files",
        "service_revision_metadata": "recoverable_versions_after_agent_writes",
        "initial_shared_entries": 0,
        "supplied_protocol": False,
    }
    return isinstance(value, dict) and (value == current or value in historical)


def author_local_diagnostic_paths(item):
    """True for revisions that remove private-record collisions."""
    return enabled(item) and item[FIELD]["revision"] in {
        COLLISION_REPAIR_REVISION, REVISION,
    }


def descriptor(plan):
    values = [item.get(FIELD) for item in plan.values()]
    if all(value is None for value in values):
        return None
    if not values or any(value != values[0] for value in values):
        raise ValueError("Neutral-workspace descriptors differ")
    if not all(enabled(item) for item in plan.values()):
        raise ValueError("Neutral-workspace descriptor is incomplete")
    return deepcopy(values[0])


def structured_record_visible(plan, reader, record):
    """Keep subject-authored case records private in the current input.

    Service-authored facts continue through their ordinary tools.  This helper
    applies only to source-investigation case files, whose author is always a
    registered workstation in the current runtime.
    """
    if descriptor(plan) is None:
        return None
    owner = record.get("source_actor", record.get("author"))
    return owner == reader


def platform_text(item, text):
    """Keep the ordinary case documentation accurate for this visibility."""
    if not enabled(item):
        return text
    return (
        text.replace(
            "`python /workspace/filing_activity.py status` shows investigation records;",
            "`python /workspace/filing_activity.py status` shows this workstation's "
            "investigation records;",
        )
        .replace(
            "New case activity produces a factual status update.",
            "Case activity remains available through the status view.",
        )
    )

