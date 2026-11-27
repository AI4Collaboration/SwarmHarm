"""Qualify one or more in-force firmware editions and optionally file their indices."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from ctags_booking_index import PROJECT, build_index, fetch, input_bytes, WORKSPACE


def check(arguments):
    parser = argparse.ArgumentParser(prog="projects.py check-index", description=__doc__)
    parser.add_argument("booking", choices=("north", "crossing", "harbor"))
    parser.add_argument("--ctags", type=Path, help="Local program (default: published software/ctags.py)")
    parser.add_argument("--edition", choices=("A", "B"))
    parser.add_argument("--output", type=Path, help="Keep the single selected index locally")
    parser.add_argument("--file-proof", action="store_true", help="File qualified indices under QA")
    parser.add_argument("--check-reference", action="store_true", help="Check against the deployed release")
    args = parser.parse_args(arguments)
    catalog = {r["name"]: r for r in json.loads(subprocess.check_output(
        [sys.executable, PROJECT, "list"]))["artifacts"]}
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        orders = [f"orders/{args.booking}.json"]
        release = f"orders/{args.booking}-release.json"
        if release in catalog or (WORKSPACE / release).is_file():
            orders.append(release)
        program = args.ctags
        names = list(orders)
        if program is None:
            if "software/ctags.py" not in catalog:
                parser.error("No published software/ctags.py is available")
            names.extend(n for n in catalog if n.startswith("software/"))
        contents = fetch(catalog, names, root)
        editions = {r["approved_edition"] for name in orders
                    if (r := json.loads(input_bytes(contents, name)))["booking"] == args.booking
                    and r["status"] == "in force"}
        if not editions or not editions <= {"A", "B"} or (args.edition and args.edition not in editions):
            parser.error("Selected booking edition has no in-force order")
        if args.edition:
            editions = {args.edition}
        if args.output and len(editions) != 1:
            parser.error("Choose --edition A or B for a single --output file")
        if program is None:
            for name in names:
                if name.startswith("software/"):
                    (root / "fetched" / name).write_bytes(contents[name])
            program = root / "fetched/software/ctags.py"
        status = 0
        for edition in sorted(editions):
            output = args.output or (root / f"{edition}.tags" if args.file_proof else None)
            verify = args.check_reference or args.file_proof or args.ctags is None
            result = build_index("check-index", args.booking, program, verify, output, edition)
            status = max(status, result)
            if result == 0 and args.file_proof:
                name = f"qa/ctags/bookings/{args.booking}/{edition}.tags"
                digest = hashlib.sha256(output.read_bytes()).hexdigest()
                prior = catalog.get(name, {})
                if prior.get("sha256") == digest:
                    print(json.dumps(prior), flush=True)
                    continue
                saved = json.loads(subprocess.check_output([sys.executable, PROJECT, "write", name,
                                   output, "--if-version", str(prior.get("version", 0))]))
                if saved["name"] != name or saved["sha256"] != digest:
                    raise ValueError(f"Filed bytes differ from the qualified index: {name}")
                print(json.dumps(saved), flush=True)
        return status
