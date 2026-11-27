"""Inspect one published Cppcheck XML report using the firmware desk's importer."""
import argparse
from dataclasses import asdict
import json

from diagnostic_records import read_xml
from published_inputs import published_inputs

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("booking", choices=("north", "crossing", "harbor"))
args = parser.parse_args()
report = f"diagnostics/{args.booking}.xml"
try:
    with published_inputs((report,), {}) as root:
        records = read_xml((root / report).read_text())
except (KeyError, FileNotFoundError):
    parser.exit(1, f"No published report at {report}\n")
print(json.dumps([asdict(record) for record in records], indent=2))
