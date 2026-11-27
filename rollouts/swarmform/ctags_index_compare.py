"""Inspect or issue the selected Ctags index for one booking."""
import argparse
import csv
from dataclasses import asdict
from difflib import unified_diff
import hashlib
import io
from itertools import islice
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from index_tools.tag_records import read_records

PROJECT = Path(__file__).with_name("projects.py")


def current_object(catalog, name, output):
    item = catalog.get(name)
    if item is None:
        raise ValueError(f"No issued project object at {name}")
    completed = subprocess.check_output([sys.executable, PROJECT, "read", name, "--version",
                                         str(item["version"]), "--output", str(output)])
    receipt = json.loads(completed)
    data = output.read_bytes()
    if receipt["sha256"] != item["sha256"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise ValueError(f"The retrieved bytes differ from {name} v{item['version']}")
    return data


def inspect_index(operation, booking, local):
    listed = json.loads(subprocess.check_output([sys.executable, PROJECT, "list"]))
    catalog = {row["name"]: row for row in listed["artifacts"]}
    with TemporaryDirectory() as work:
        output = Path(work) / "item"
        manifest = current_object(catalog, "indices/bookings.csv", output)
        orders = {row["booking"]: row["release_file"] for row in csv.DictReader(io.StringIO(manifest.decode()))}
        if booking not in orders:
            raise ValueError("Unknown booking. Choose one of " + ", ".join(orders))
        name = orders[booking]
        draft = local.read_bytes()
        if operation == "issue-index":
            records = read_records(draft.decode())
            output.write_bytes(draft)
            previous = catalog.get(name, {}).get("version", 0)
            completed = subprocess.check_output([sys.executable, PROJECT, "write", name, str(output),
                                                 "--if-version", str(previous)])
            receipt = json.loads(completed)
            if receipt["sha256"] != hashlib.sha256(draft).hexdigest():
                raise ValueError(f"Published bytes differ from the selected file: {name}")
            print(json.dumps({"booking": booking, "records": len(records), "release": receipt}))
            return 0
        issued = current_object(catalog, name, output)
    before, after = ([json.dumps(asdict(record), ensure_ascii=False) for record in read_records(data.decode())]
                     for data in (issued, draft))
    print(f"{name} v{catalog[name]['version']}  {len(before)} issued records, {len(after)} local records")
    if issued == draft:
        print("Index bytes match.")
        return 0
    if before == after:
        print("Index bytes differ. Parsed symbol records match in order.")
        return 1
    lines = unified_diff(before, after, fromfile=f"{name} (issued)", tofile=str(local), n=1, lineterm="")
    for line in islice(lines, 60):
        print(line)
    if next(lines, None) is not None:
        print("Further record differences omitted.")
    return 1


def main(operation, arguments):
    parser = argparse.ArgumentParser(prog="projects.py " + operation, description=__doc__)
    parser.add_argument("booking")
    parser.add_argument("file", type=Path)
    args = parser.parse_args(arguments)
    try:
        return inspect_index(operation, args.booking, args.file)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"{error}\n")
