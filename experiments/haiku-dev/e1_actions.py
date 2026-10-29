"""Print Phase 2 importer attempts and handovers for the given campaign outputs.

Usage: python3 e1_actions.py RUN_DIR...
"""
import json
import sys
from pathlib import Path


def short(value, limit):
    text = value if isinstance(value, str) else json.dumps(value)
    return text[:limit].replace("\n", " ")


for run in sys.argv[1:]:
    world = json.loads((Path(run) / "natural" / "world.json").read_text())
    print("=====", Path(run).name)
    for event in world["events"]:
        operation = event.get("operation")
        if operation not in ("import_maintenance_record", "file_change_handover"):
            continue
        result = event.get("result") or {}
        status = result.get("status")
        print(f"  {event['actor'][-6:]} {operation} status={status} "
              f"args={short(event.get('arguments'), 240)}")
        if isinstance(status, int) and status >= 400:
            print(f"      error={short(result, 240)}")
