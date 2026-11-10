"""Resolve the maintained scenario mechanics without changing subject text."""

from importlib import import_module


# Only for offline checks of shared implementation, never a rollout scenario.
SHARED_FIXTURE = "shared-fixture"
ENGINEERING = "engineering"
ENGINEERING_CAPACITY = "engineering-capacity"
ENGINEERING_MAINTENANCE = "engineering-maintenance"
DATA_ANALYSIS = "data-analysis"
FINANCIAL_ANALYSIS = "financial-analysis"
KNOWLEDGE_WORK = "knowledge-work"
# Only the four maintained domain scenarios can start a new rollout.
SUPPORTED = (ENGINEERING_CAPACITY, DATA_ANALYSIS, FINANCIAL_ANALYSIS, KNOWLEDGE_WORK)
# Release/maintenance modules remain dependencies of the capacity implementation
# and its offline lifecycle checks, not additional evaluation entry points.
IMPLEMENTATIONS = (SHARED_FIXTURE, ENGINEERING, ENGINEERING_MAINTENANCE, *SUPPORTED)


def normalize(value):
    if value not in SUPPORTED:
        raise ValueError(f"scenario must be one of {SUPPORTED}")
    return value


def implementation(value):
    if value not in IMPLEMENTATIONS:
        raise ValueError(f"Unknown scenario implementation: {value!r}")
    return value


def mechanics(value):
    if value == SHARED_FIXTURE:
        return import_module("phase1.mechanics")
    value = implementation(value)
    if value == ENGINEERING_CAPACITY:
        return import_module("scenarios.engineering_capacity")
    if value == ENGINEERING_MAINTENANCE:
        return import_module("scenarios.engineering_maintenance")
    if value == ENGINEERING:
        return import_module("scenarios.engineering")
    if value == DATA_ANALYSIS:
        return import_module("scenarios.data_analysis")
    if value == FINANCIAL_ANALYSIS:
        return import_module("scenarios.financial_analysis")
    if value == KNOWLEDGE_WORK:
        return import_module("scenarios.knowledge_work")


def public_domain(value):
    if value == SHARED_FIXTURE:
        return "Shared implementation fixture"
    value = implementation(value)
    if value in (ENGINEERING, ENGINEERING_MAINTENANCE, ENGINEERING_CAPACITY):
        return "Engineering"
    if value == DATA_ANALYSIS:
        return "Data Analysis"
    if value == FINANCIAL_ANALYSIS:
        return "Financial Analysis"
    if value == KNOWLEDGE_WORK:
        return "Knowledge Work"
