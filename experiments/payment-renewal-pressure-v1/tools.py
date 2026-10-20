"""Unchanged ordinary business tools for the cash-funding condition."""
import importlib.util
from pathlib import Path


def tools(channel='shared'):
    path = Path(__file__).resolve().parents[2]/'experiments/payment-route-transfer-v1/tools.py'
    spec = importlib.util.spec_from_file_location('liquidity_tools_parent', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.tools(channel)
