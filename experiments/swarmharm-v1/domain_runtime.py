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
SUPPORTED = (ENGINEERING, ENGINEERING_MAINTENANCE, ENGINEERING_CAPACITY, DATA_ANALYSIS, FINANCIAL_ANALYSIS, KNOWLEDGE_WORK)


def normalize(value):
    if value not in SUPPORTED:
        raise ValueError(f"scenario must be one of {SUPPORTED}")
    return value


def mechanics(value):
    if value == SHARED_FIXTURE:
        return import_module("mechanics")
    value = normalize(value)
    if value == ENGINEERING_CAPACITY:
        return import_module("domains.engineering_capacity")
    if value == ENGINEERING_MAINTENANCE:
        return import_module("domains.engineering_maintenance")
    if value == ENGINEERING:
        return import_module("domains.engineering")
    if value == DATA_ANALYSIS:
        return import_module("domains.data_analysis")
    if value == FINANCIAL_ANALYSIS:
        return import_module("domains.financial_analysis")
    if value == KNOWLEDGE_WORK:
        return import_module("domains.knowledge_work")


def public_domain(value):
    if value == SHARED_FIXTURE:
        return "Shared implementation fixture"
    value = normalize(value)
    if value in (ENGINEERING, ENGINEERING_MAINTENANCE, ENGINEERING_CAPACITY):
        return "Engineering"
    if value == DATA_ANALYSIS:
        return "Data Analysis"
    if value == FINANCIAL_ANALYSIS:
        return "Financial Analysis"
    if value == KNOWLEDGE_WORK:
        return "Knowledge Work"


def continuation_module(value):
    if value == SHARED_FIXTURE:
        return "continuation"
    value = normalize(value)
    if value == ENGINEERING_CAPACITY:
        return "domains.engineering_capacity_continuation"
    if value == ENGINEERING_MAINTENANCE:
        return "domains.engineering_maintenance_continuation"
    if value == ENGINEERING:
        return "domains.engineering_continuation"
    if value == DATA_ANALYSIS:
        return "domains.data_analysis_continuation"
    if value == FINANCIAL_ANALYSIS:
        return "domains.financial_analysis_continuation"
    if value == KNOWLEDGE_WORK:
        return "domains.knowledge_work_continuation"


def integrated_review_module(value):
    if value == SHARED_FIXTURE:
        return "integrated_review"
    value = normalize(value)
    if value == ENGINEERING_CAPACITY:
        return "domains.engineering_capacity_review"
    if value == ENGINEERING_MAINTENANCE:
        return "domains.engineering_maintenance_review"
    if value == ENGINEERING:
        return "domains.engineering_integrated_review"
    if value == DATA_ANALYSIS:
        return "domains.data_analysis_integrated_review"
    if value == FINANCIAL_ANALYSIS:
        return "domains.financial_analysis_integrated_review"
    if value == KNOWLEDGE_WORK:
        return "domains.knowledge_work_integrated_review"

