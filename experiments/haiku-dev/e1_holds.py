"""Relate held bookings to the replicas that host the restore points others rely on.

Usage: python3 e1_holds.py RUN_DIR...
"""
import collections
import json
import sys
from pathlib import Path

for run in sys.argv[1:]:
    root = Path(run)
    review = json.loads((root / "independent-review.json").read_text())
    joint = review["phase2"]["collective_outcomes"][0]["joint"]
    world = json.loads((root / "natural" / "world.json").read_text())
    imports = [e for e in world["events"] if e.get("operation") == "import_maintenance_record"]
    failed = [e for e in imports if (e.get("result") or {}).get("status") == 422]
    hosts = {}
    for event in failed:
        hosts[event["arguments"]["restore_reference"]] = event["arguments"]["replica_id"]
    uses = collections.Counter(b["restore_reference"] for b in joint["bookings"])
    print("=====", root.name, "| import attempts", len(imports), "| 422 own-replica", len(failed),
          "| agents attempting import", len({e["actor"] for e in imports}))
    for booking in joint["bookings"]:
        reference = booking["restore_reference"]
        print(f"  {booking['replica_id']} {booking['execution_state']:9} restore={reference[-6:]} "
              f"host={hosts.get(reference, '?')} used_by={uses[reference]}")
    print("  remaining 3.8 sources:", joint["remaining_version38_sources"])
