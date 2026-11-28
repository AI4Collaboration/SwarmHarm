"""Track the currently submitted candidate and compare two chosen builds on one booking."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from difflib import unified_diff
from itertools import islice
from tempfile import TemporaryDirectory

from ctags_candidate import cli, unpack
from ctags_qualification import check

PENDING = "staging/ctags/current-build.json"


def catalog():
    return {row["name"]: row for row in cli("list")["artifacts"]}


def register(receipt, root):
    body = json.dumps({k: receipt[k] for k in ("name", "version", "sha256")}, sort_keys=True).encode()
    digest = hashlib.sha256(body).hexdigest()
    path = root / "pending-build.json"
    path.write_bytes(body)
    for attempt in range(4):
        last = catalog().get(PENDING, {})
        if last.get("sha256") == digest:
            return
        version = last.get("version", 0)
        try:
            saved = cli("write", PENDING, path, "--if-version", str(version))
        except subprocess.CalledProcessError:
            if attempt < 3 and catalog().get(PENDING, {}).get("version", 0) != version:
                continue
            raise
        if saved["name"] != PENDING or saved["sha256"] != digest:
            raise ValueError("Pending registration receipt mismatch")
        return


def pending_build(rows):
    pointer = rows.get(PENDING)
    if pointer is None:
        return None
    receipt = cli("read", PENDING, "--version", str(pointer["version"]))
    text = receipt["text"]
    if (receipt["name"] != PENDING or receipt["version"] != pointer["version"]
            or hashlib.sha256(text.encode()).hexdigest() != pointer["sha256"]):
        raise ValueError("Pending build selection changed")
    selected = json.loads(text)
    if not re.fullmatch(r"candidates/ctags/[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.json", selected["name"]):
        raise ValueError("Invalid pending candidate name")
    if any(rows.get(selected["name"], {}).get(k) != selected[k] for k in ("version", "sha256")):
        raise ValueError("Pending candidate does not match the stored immutable package")
    return selected


def check_selected(name, booking, edition):
    rows = catalog()
    pending = pending_build(rows)
    args = [booking, "--check-reference"]
    if edition:
        args += ["--edition", edition]
    if pending is None and name is None:
        return check(args, rows=rows)
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        def load(row, folder):
            directory = root / folder
            directory.mkdir()
            unpack(row["name"], directory, version=row["version"], expected=row["sha256"])
            return directory / "software/ctags.py"
        selected = rows.get(name) if name else pending
        if not selected:
            raise ValueError(f"Candidate unavailable: {name}")
        first = load(selected, "selected")
        if name is None:
            # A normal project check runs the complete installed staging build.
            return check([*args, "--ctags", str(first)], rows=rows)
        first_label = f"{selected['name']} v{selected['version']} {selected['sha256']}"
        if name and pending and pending["name"] != name:
            second = load(pending, "pending")
            args += ["--ctags", str(second)]
            second_label = f"{pending['name']} v{pending['version']} {pending['sha256']}"
        elif "software/ctags.py" in rows:
            live = rows["software/ctags.py"]
            second_label = f"{live['name']} v{live['version']} {live['sha256']}"
        else:
            print("No deployed indexer is available; qualifying the selected candidate against the reference.", flush=True)
            return check([*args, "--ctags", str(first)], rows=rows)
        print(f"Comparing {first_label} with {second_label}", flush=True)
        return check(args, comparison=(first, first_label, second_label), rows=rows)


def compare(comparison, run, work, job, source, booking, edition):
    program, first_label, second_label = comparison
    other = work / "comparison"
    other.mkdir()
    (other / "meters.cpp").write_bytes(source)
    first = subprocess.run([sys.executable, program, *job["argv"]], cwd=other,
                           stdin=subprocess.DEVNULL, capture_output=True)
    print(f"{booking}/{edition}: selected exit {first.returncode}, comparison exit {run.returncode}", flush=True)
    different = first.returncode != run.returncode
    for channel in ("stdout", "stderr"):
        a, b = getattr(first, channel), getattr(run, channel)
        if a == b:
            print(f"{channel}: {len(a)} identical bytes, SHA-256 {hashlib.sha256(a).hexdigest()}")
            continue
        different = True
        print(f"{channel}: {len(a)} vs {len(b)} bytes")
        changes = unified_diff(a.decode(errors="replace").splitlines(), b.decode(errors="replace").splitlines(),
                               fromfile=first_label, tofile=second_label, lineterm="")
        for line in islice(changes, 80):
            print(line)
    return different
