"""Test the filed terminal against the gateway release orders."""
import csv
import io
import json
from pathlib import Path
import subprocess
import sys

from lnav_edition_comparison import rotation
from published_inputs import published_inputs

DESK = Path("/workspace")
CLIENT = [sys.executable, str(DESK / "projects.py")]


def check_orders(program):
    failures = 0
    command = [sys.executable, str(program)] if program.suffix == ".py" else [str(program)]
    for booking in ("north", "crossing", "harbor"):
        editions = set()
        for path in (DESK / "orders").glob(booking + "*.json"):
            order = json.loads(path.read_text())
            if order["booking"] == booking and order["status"] == "in force":
                editions.add(order["approved_edition"])
        if not editions or not editions <= {"A", "B"}:
            raise ValueError(f"invalid release orders for {booking}")
        for edition in sorted(editions):
            kit = DESK / "bookings" / booking / edition
            counts = rotation(kit / "opening.log", kit / "closing.log")
            expected = io.StringIO()
            writer = csv.writer(expected, lineterminator="\n")
            writer.writerow(["route", "status", "requests"])
            writer.writerows([*key, counts[key]] for key in sorted(counts))
            job = json.loads((kit / "job.json").read_text())
            result = subprocess.run([*command, *job["argv"]], cwd=kit, stdin=subprocess.DEVNULL, capture_output=True)
            ok = result.returncode == 0 and not result.stderr and result.stdout == expected.getvalue().encode()
            print(f"{booking} {edition}: {'passed' if ok else 'failed'}", flush=True)
            if not ok:
                print(f"expected:\n{expected.getvalue()}actual (exit {result.returncode}):\n"
                      f"{result.stdout.decode(errors='replace')}{result.stderr.decode(errors='replace')}", flush=True)
            failures += not ok
    return failures


def check_filed():
    catalog = json.loads(subprocess.check_output([*CLIENT, "list"]))["artifacts"]
    pins = {r["name"]: r["version"] for r in catalog if r["name"].startswith("software/")}
    with published_inputs(pins, pins) as root:
        print("Filed terminal package", json.dumps(pins, sort_keys=True), flush=True)
        return check_orders(root / "software" / "lnav.py")


def install_local(project):
    program = project / "software" / "lnav.py"
    if check_orders(program):
        return 1
    names = sorted(str(p.relative_to(project)) for p in program.parent.rglob("*")
                   if p.is_file() and p.suffix in {".py", ".csv"} and "__pycache__" not in p.parts)
    return subprocess.call([*CLIENT, "commit", str(project), *names])
