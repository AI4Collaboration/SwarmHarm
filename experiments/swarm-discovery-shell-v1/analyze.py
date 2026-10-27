"""Reuse the provider-aware native/ATIF auditor in a separate process."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().parent.parent/'swarm-discovery-parallel-v1/analyze.py'),run_name='__main__')
