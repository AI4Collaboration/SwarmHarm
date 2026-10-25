"""Resolve the maintained scenario mechanics without changing subject text."""

from importlib import import_module


PILOT = "procurement-pilot"
ENGINEERING = "engineering"
DATA_ANALYSIS = "data-analysis"
SUPPORTED = (PILOT, ENGINEERING, DATA_ANALYSIS)


def normalize(value):
    value = value or PILOT
    if value not in SUPPORTED:
        raise ValueError(f"scenario must be one of {SUPPORTED}")
    return value


def mechanics(value):
    value = normalize(value)
    if value == ENGINEERING:
        return import_module("domains.engineering")
    if value == DATA_ANALYSIS:
        return import_module("domains.data_analysis")
    return import_module("mechanics")


def public_domain(value):
    value = normalize(value)
    if value == ENGINEERING:
        return "Engineering"
    if value == DATA_ANALYSIS:
        return "Data Analysis"
    return "Procurement pilot"


def continuation_module(value):
    value = normalize(value)
    if value == ENGINEERING:
        return "domains.engineering_continuation"
    if value == DATA_ANALYSIS:
        return "domains.data_analysis_continuation"
    return "continuation"


def integrated_review_module(value):
    value = normalize(value)
    if value == ENGINEERING:
        return "domains.engineering_integrated_review"
    if value == DATA_ANALYSIS:
        return "domains.data_analysis_integrated_review"
    return "integrated_review"

