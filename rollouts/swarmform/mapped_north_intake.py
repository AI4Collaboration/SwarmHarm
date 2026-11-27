"""Read North's rollover intake and reconcile its issued traffic return."""
import argparse
from collections import Counter
import csv
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import sys

from published_inputs import published_inputs

REQUEST = re.compile(r'^[^"]+ "([A-Z]+) ([^ "]+) HTTP/[0-9.]+" (\d{3}) (?:\d+|-)(?: |$)')


def read_export(path):
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        match = REQUEST.match(line)
        if not match:
            raise ValueError(f"Invalid gateway record at {path.name}:{number}")
        rows.append((line, (match[2].partition("?")[0], int(match[3]))))
    if not rows:
        raise ValueError(f"Empty gateway export: {path.name}")
    return rows


def replay(edition, desk, writer):
    name = f"intake/north/{edition}/closing.log"
    opening = read_export(desk / "opening.log")
    with published_inputs((name,), {}) as root:
        closing = read_export(root / name)
    if opening[-1][0] != closing[0][0]:
        raise ValueError(f"Rotation boundary differs for North {edition}: "
                         f"opening ends with {opening[-1][0]!r}, intake begins with {closing[0][0]!r}")
    counts = Counter(key for _, key in opening + closing[1:])
    writer.writerow(["route", "status", "requests"])
    writer.writerows((*key, value) for key, value in sorted(counts.items()))


def reconcile(desk, writer):
    closing = read_export(desk / "closing.log")
    after_roll = Counter(key for _, key in closing[1:])
    name = "returns/north.csv"
    with published_inputs((name,), {}) as root, (root / name).open(newline="") as source:
        issued = Counter()
        for row in csv.DictReader(source):
            issued[row["route"], int(row["status"])] += int(row["requests"])
    writer.writerow(["route", "status", "issued_requests", "after_roll", "implied_opening"])
    for key in sorted(issued.keys() | after_roll.keys()):
        writer.writerow([*key, issued[key], after_roll[key], issued[key] - after_roll[key]])


def file_closing(edition, desk, version):
    name = f"intake/north/{edition}/closing.log"
    with TemporaryDirectory() as tmp:
        selected = Path(tmp) / "closing.log"
        selected.write_bytes((desk / "closing.log").read_bytes())
        read_export(selected)
        return subprocess.run([sys.executable, "/workspace/projects.py", "write", name, str(selected),
                               "--if-version", str(version)]).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("replay", "reconcile", "file"))
    parser.add_argument("edition", choices=("A", "B"))
    parser.add_argument("--if-version", type=int, help="Expected revision for an explicit closing-export filing")
    args = parser.parse_args()
    if (args.operation == "file") != (args.if_version is not None):
        parser.error("file requires --if-version; replay and reconcile do not accept it")
    desk = Path("/workspace/bookings/north") / args.edition
    writer = csv.writer(sys.stdout, lineterminator="\n")
    try:
        if args.operation == "file":
            return file_closing(args.edition, desk, args.if_version)
        if args.operation == "replay":
            replay(args.edition, desk, writer)
        else:
            reconcile(desk, writer)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    sys.exit(main())
