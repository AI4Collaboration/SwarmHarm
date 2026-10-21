"""Unchanged v2 business world for a natural source-boundary diagnostic."""
from pathlib import Path
import importlib.util

REPO = Path(__file__).resolve().parents[2]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


parent = module("sol_misalignment_parent_world", REPO / "experiments/hf-method-v2/world.py")
FleetWorld, inputs, digest, base = parent.FleetWorld, parent.inputs, parent.digest, parent.base
CampaignWorld = base.CampaignWorld
