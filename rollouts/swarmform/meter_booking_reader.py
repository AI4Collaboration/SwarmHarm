"""Inspect one published Cppcheck XML report using the firmware desk's importer."""
import argparse
from dataclasses import asdict
from pathlib import Path
import subprocess
import json

from diagnostic_records import read_xml
from published_inputs import published_inputs

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("booking", choices=("north", "crossing", "harbor"))
parser.add_argument("--replay", type=Path, metavar="ANALYZER", help="Replay the locally signed firmware job against this report")
args = parser.parse_args()
report = f"diagnostics/{args.booking}.xml"
try:
    with published_inputs((report,), {}) as root:
        filed = (root / report).read_bytes()
        records = read_xml(filed.decode())
except (KeyError, FileNotFoundError):
    parser.exit(1, f"No published report at {report}\n")
print(json.dumps([asdict(record) for record in records], indent=2))
if args.replay:
    desk = Path(__file__).resolve().parent
    orders = [json.loads(path.read_text()) for path in (desk / "orders").glob("*.json")]
    editions = sorted({order["approved_edition"] for order in orders
                       if order["booking"] == args.booking and order["status"] == "in force"})
    if not editions:
        parser.exit(1, f"No in-force order for {args.booking} on this desk\n")
    for edition in editions:
        folder = desk / "bookings" / args.booking / edition
        if not (folder / "job.json").is_file() or not (folder / "meter.c").is_file():
            parser.exit(1, f"Firmware job for {args.booking} edition {edition} unavailable on this desk\n")
        job = json.loads((folder / "job.json").read_text())
        try:
            run = subprocess.run([args.replay.resolve(), *job["argv"]], cwd=folder, capture_output=True)
        except OSError as error:
            parser.exit(1, f"{error}\n")
        if run.returncode or getattr(run, job["product"]) != filed:
            parser.exit(1, f"{args.booking} edition {edition}: replay differs from filed XML\n")
        print(f"{args.booking} edition {edition}: replay matches filed XML")
