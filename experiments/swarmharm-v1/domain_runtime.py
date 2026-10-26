"""Resolve the maintained scenario mechanics without changing subject text."""

from importlib import import_module


PILOT = "procurement-pilot"
ENGINEERING = "engineering"
ENGINEERING_MAINTENANCE = "engineering-maintenance"
DATA_ANALYSIS = "data-analysis"
FINANCIAL_ANALYSIS = "financial-analysis"
KNOWLEDGE_WORK = "knowledge-work"
SUPPORTED = (PILOT, ENGINEERING, ENGINEERING_MAINTENANCE, DATA_ANALYSIS, FINANCIAL_ANALYSIS, KNOWLEDGE_WORK)


def normalize(value):
    value = value or PILOT
    if value not in SUPPORTED:
        raise ValueError(f"scenario must be one of {SUPPORTED}")
    return value


def mechanics(value):
    value = normalize(value)
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
    return import_module("mechanics")


def public_domain(value):
    value = normalize(value)
    if value in (ENGINEERING, ENGINEERING_MAINTENANCE):
        return "Engineering"
    if value == DATA_ANALYSIS:
        return "Data Analysis"
    if value == FINANCIAL_ANALYSIS:
        return "Financial Analysis"
    if value == KNOWLEDGE_WORK:
        return "Knowledge Work"
    return "Procurement pilot"


def continuation_module(value):
    value = normalize(value)
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
    return "continuation"


def integrated_review_module(value):
    value = normalize(value)
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
    return "integrated_review"

