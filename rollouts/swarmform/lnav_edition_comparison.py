"""Compare both gateway editions with the filed traffic return."""
import argparse
from collections import Counter
import csv
from pathlib import Path
import sys

from north_intake import read_export
from published_inputs import published_inputs


def rotation(opening, closing):
    before = read_export(opening)
    after = read_export(closing)
    if before[-1][0] != after[0][0]:
        raise ValueError(f"rotation boundaries differ: {opening} and {closing}")
    return Counter(key for _, key in before + after[1:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("booking", choices=("north", "crossing", "harbor"))
    args = parser.parse_args()
    desk = Path("/workspace")
    booking = args.booking
    filed = f"returns/{booking}.csv"
    names = [filed]
    records = {}
    for edition in ("A", "B"):
        for roll in ("opening", "closing"):
            name = f"bookings/{booking}/{edition}/{roll}.log"
            if not (desk / name).is_file():
                if booking == "north" and roll == "closing":
                    name = f"intake/north/{edition}/closing.log"
                names.append(name)
            records[edition, roll] = name
    try:
        with published_inputs(names, {}) as project:
            def source(name):
                return (project if name in names else desk) / name

            counts = {edition: rotation(source(records[edition, "opening"]),
                                        source(records[edition, "closing"])) for edition in ("A", "B")}
            issued = {}
            with source(filed).open(newline="") as stream:
                reader = csv.DictReader(stream)
                if reader.fieldnames != ["route", "status", "requests"]:
                    raise ValueError(f"unexpected columns in {filed}")
                for row in reader:
                    key = row["route"], int(row["status"])
                    if key in issued:
                        raise ValueError(f"duplicate filed row {key}")
                    issued[key] = int(row["requests"])
        writer = csv.writer(sys.stdout, lineterminator="\n")
        writer.writerow(["booking", "route", "status", "issued_requests", "edition_A_requests", "edition_B_requests"])
        for key in sorted(issued.keys() | counts["A"].keys() | counts["B"].keys()):
            writer.writerow([booking, *key, issued.get(key, ""), counts["A"].get(key, ""), counts["B"].get(key, "")])
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
