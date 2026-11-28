"""Inspect survey or ledger materials delivered to this station."""
import argparse
import json
from pathlib import Path


def inspect(workspace, booking, edition):
    directory = workspace / "bookings" / booking / edition
    job = directory / "job.json"
    present = sorted(path.name for path in directory.glob("*") if path.is_file())
    required = {"job.json"}
    if job.is_file():
        recipe = json.loads(job.read_bytes())
        if recipe["stdin"] is None:
            required.update((recipe["argv"][-1], "calibration.svg"))
        else:
            required.update((recipe["stdin"], "loads.csv"))
    return {"booking": booking, "edition": edition, "present": present,
            "missing": sorted(required.difference(present)), "job_available": job.is_file()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("booking", choices=("north", "crossing", "harbor"))
    args = parser.parse_args()
    print(json.dumps([inspect(Path("/workspace"), args.booking, edition) for edition in ("A", "B")]))
