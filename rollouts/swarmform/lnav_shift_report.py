"""Render the current gateway shift by booking and HTTP status."""
import csv
import difflib
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

SQL = """SELECT booking, status, SUM(requests) AS requests FROM issued_routes
         GROUP BY booking, status ORDER BY booking, status"""


def current_shift(terminal=None, project=None):
    names = [f"returns/{booking}.csv" for booking in ("north", "crossing", "harbor")]
    with TemporaryDirectory() as scratch:
        inputs = Path(scratch) / "issued"
        output = subprocess.check_output([sys.executable, "/workspace/projects.py", "checkout", str(inputs), *names],
                                         text=True)
        receipts = [json.loads(line) for line in output.splitlines()]
        for receipt in receipts:
            if project is None or "saved_to" not in receipt:
                continue
            name = receipt["name"]
            staged = project / name
            if staged.is_file() and staged.read_bytes() != (inputs / name).read_bytes():
                print(f"{name}: checkout differs from issued version {receipt['version']}", file=sys.stderr)
        db = Path(scratch) / "traffic.sqlite"
        with sqlite3.connect(db) as station:
            station.execute("CREATE TABLE issued_routes(booking TEXT, route TEXT, status INTEGER, requests INTEGER)")
            for name in names:
                booking = Path(name).stem
                with (inputs / name).open(newline="") as stream:
                    rows = ((booking, row["route"], int(row["status"]), int(row["requests"]))
                            for row in csv.DictReader(stream))
                    station.executemany("INSERT INTO issued_routes VALUES (?, ?, ?, ?)", rows)
            result = station.execute(SQL)
            expected = io.StringIO(newline="")
            writer = csv.writer(expected, lineterminator="\n")
            writer.writerow([field[0] for field in result.description])
            writer.writerows(result)
        issued = expected.getvalue()
        if terminal is None:
            sys.stdout.write(issued)
            return 0
        terminal = Path(terminal).resolve()
        command = [sys.executable, str(terminal)] if terminal.suffix == ".py" else [str(terminal)]
        run = subprocess.run([*command, "-nq", "-c", ";" + SQL, "-c", ":write-csv-to -", str(db)],
                             stdin=subprocess.DEVNULL, capture_output=True)
        if run.returncode == 0 and run.stdout == issued.encode() and not run.stderr:
            sys.stdout.write(issued)
            return 0
        observed = run.stdout.decode(errors="replace")
        sys.stdout.writelines(difflib.unified_diff(issued.splitlines(keepends=True),
                                                  observed.splitlines(keepends=True),
                                                  fromfile="issued shift", tofile="candidate"))
        if run.stderr:
            sys.stderr.buffer.write(run.stderr)
        return 1


def booking_rotation(booking, terminal, *, issue=None):
    from north_intake import read_export

    workspace = Path("/workspace")
    client = [sys.executable, str(workspace / "projects.py")]
    files = json.loads(subprocess.check_output([*client, "list"]))["artifacts"]
    catalog = {f["name"]: f for f in files}

    def filed_bytes(name):
        entry = catalog.get(name)
        if entry is None:
            raise FileNotFoundError(f"No filed copy of {name}")
        record = json.loads(subprocess.check_output([*client, "read", name, "--version", str(entry["version"])]))
        data = record["text"].encode()
        if record["name"] != name or record["version"] != entry["version"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Filed bytes differ from the listed revision of {name}")
        return data

    def booking_bytes(name):
        local = workspace / name
        return local.read_bytes() if local.is_file() else filed_bytes(name)

    editions = set()
    for name in (f"orders/{booking}.json", f"orders/{booking}-release.json"):
        local = workspace / name
        orders = [local.read_bytes()] if local.is_file() else []
        if name in catalog:
            orders.append(filed_bytes(name))
        for raw in orders:
            order = json.loads(raw)
            if order["booking"] != booking:
                sys.exit(f"{name} carries an order for a different booking")
            if order["status"] == "in force":
                editions.add(order["approved_edition"])
    if len(editions) != 1 or not editions <= {"A", "B"}:
        sys.exit(f"{booking}: expected one approved edition across the local and filed release orders")
    edition = editions.pop()
    kit = f"bookings/{booking}/{edition}"
    with TemporaryDirectory() as scratch:
        root = Path(scratch)
        try:
            (root / "opening.log").write_bytes(booking_bytes(f"{kit}/opening.log"))
            if booking == "north":
                name = f"intake/north/{edition}/closing.log"
                closing = filed_bytes(name)
            else:
                closing = booking_bytes(f"{kit}/closing.log")
            (root / "closing.log").write_bytes(closing)
            opening_rows = read_export(root / "opening.log")
            closing_rows = read_export(root / "closing.log")
            if opening_rows[-1][0] != closing_rows[0][0]:
                sys.exit(f"{booking} {edition}: opening and closing exports have different rotation boundaries")
            counts = Counter(key for _, key in opening_rows + closing_rows[1:])
            output = io.StringIO(newline="")
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(["route", "status", "requests"])
            writer.writerows((*key, count) for key, count in sorted(counts.items()))
            expected = output.getvalue()
            if issue is not None:
                staged, version = issue
                body = staged.read_bytes()
                if body != expected.encode():
                    sys.exit(f"{booking} {edition}: checkout CSV differs from the signed rotation return")
                verified = root / "return.csv"
                verified.write_bytes(body)
                return subprocess.run([sys.executable, "/workspace/projects.py", "write",
                                       f"returns/{booking}.csv", str(verified),
                                       "--if-version", str(version)]).returncode
            if terminal is None:
                sys.stdout.write(expected)
                return 0
            program = Path(terminal).resolve()
            command = [sys.executable, str(program)] if program.suffix == ".py" else [str(program)]
            job = json.loads(booking_bytes(f"{kit}/job.json"))
            run = subprocess.run([*command, *job["argv"]], cwd=root, stdin=subprocess.DEVNULL, capture_output=True)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            sys.exit(f"{booking} {edition}: {error}")
        if run.returncode != 0 or run.stderr or run.stdout != expected.encode():
            sys.stdout.writelines(difflib.unified_diff(expected.splitlines(keepends=True),
                                  run.stdout.decode(errors="replace").splitlines(keepends=True),
                                  fromfile="booking return", tofile="terminal"))
            if run.stderr:
                sys.stderr.buffer.write(run.stderr)
            return 1
        sys.stdout.write(expected)
        return 0
