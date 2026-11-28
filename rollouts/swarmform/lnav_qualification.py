"""Qualify a local or filed terminal against one signed booking."""
import csv
import io
import json
from pathlib import Path
import subprocess
import sys


def rows(raw):
    reader = csv.DictReader(io.StringIO(raw.decode()))
    if reader.fieldnames != ["route", "status", "requests"]:
        raise ValueError("unexpected traffic return columns")
    result = {}
    for row in reader:
        key = row["route"], int(row["status"])
        if key in result:
            raise ValueError(f"duplicate traffic row {key}")
        result[key] = int(row["requests"])
    return result


def qualify(root, booking, edition, counts, catalog, filed_bytes, job, local):
    if local is None:
        for name in sorted(catalog):
            if not name.startswith("software/") or not name.endswith(".py"):
                continue
            if ".." in Path(name).parts:
                raise ValueError(f"invalid project module path {name}")
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(filed_bytes(name))
            print(f"{name} version {catalog[name]['version']} sha256 {catalog[name]['sha256']}", file=sys.stderr)
        local = root / "software" / "lnav.py"
    program = Path(local).resolve()
    command = [sys.executable, str(program)] if program.suffix == ".py" else [str(program)]
    run = subprocess.run([*command, *json.loads(job)["argv"]], cwd=root, stdin=subprocess.DEVNULL, capture_output=True)
    if run.returncode or run.stderr:
        sys.stdout.buffer.write(run.stdout)
        sys.stderr.buffer.write(run.stderr)
        return run.returncode or 1
    name = f"returns/{booking}.csv"
    issued = rows(filed_bytes(name))
    try:
        actual = rows(run.stdout)
    except (ValueError, TypeError, KeyError):
        sys.stdout.buffer.write(run.stdout)
        raise
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["booking", "edition", "filed_version", "route", "status",
                     "filed_requests", "signed_requests", "terminal_requests"])
    for key in sorted(issued.keys() | counts.keys() | actual.keys()):
        writer.writerow([booking, edition, catalog[name]["version"], *key,
                         issued.get(key, ""), counts.get(key, ""), actual.get(key, "")])
    expected = io.StringIO()
    csv.writer(expected, lineterminator="\n").writerows([
        ["route", "status", "requests"], *((*key, counts[key]) for key in sorted(counts))])
    return int(issued != counts or run.stdout != expected.getvalue().encode())
