"""Reuse the unchanged documentary-settlement business interfaces."""
import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[2]/'experiments/settlement-close-v1/tools.py'
spec = importlib.util.spec_from_file_location('all_blocked_business_tools', path)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
tools = base.tools
