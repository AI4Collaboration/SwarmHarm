"""Resolve the maintained scenario mechanics without changing subject text."""

from importlib import import_module


PILOT = "procurement-pilot"
ENGINEERING = "engineering"
SUPPORTED = (PILOT, ENGINEERING)


def normalize(value):
    value = value or PILOT
    if value not in SUPPORTED:
        raise ValueError(f"scenario must be one of {SUPPORTED}")
    return value


def mechanics(value):
    value = normalize(value)
    if value == ENGINEERING:
        return import_module("domains.engineering")
    return import_module("mechanics")


def public_domain(value):
    value = normalize(value)
    return "Engineering" if value == ENGINEERING else "Procurement pilot"

