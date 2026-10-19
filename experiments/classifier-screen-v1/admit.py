"""Read-only admission check for a new, explicitly named task."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def assert_allowed(family, task):
    active = json.loads((ROOT / "data/task-quarantine/active.json").read_text())
    selected = [row for row in active["held_tasks"] if row["family"] == family and row["task"] == task]
    if selected:
        raise ValueError(f"Task is held: {family}/{task}. Review data/task-quarantine/{active['manifest']} before new admission.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", required=True)
    parser.add_argument("--task", required=True)
    args = parser.parse_args()
    assert_allowed(args.family, args.task)
    print("No quarantine entry for this task. Other study gates still apply.")
