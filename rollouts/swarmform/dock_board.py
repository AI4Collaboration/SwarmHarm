"""Display the last issued load-desk statements for one dispatch shift."""
import argparse
import csv
from hashlib import sha256
import json

from published_inputs import published_inputs

FIELDS = {
    "north": ("dock", "shift", "source_shift", "measured_kg", "readings"),
    "crossing": ("shift", "docks", "known_docks", "weighed_this_shift", "last_known_total_kg"),
    "harbor": ("dock", "shift", "source_shift", "measured_kg", "basis"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shift", type=int)
    parser.add_argument("booking", nargs="?", choices=FIELDS)
    args = parser.parse_args()
    bookings = (args.booking,) if args.booking else FIELDS
    paths = {booking: f"ledgers/{booking}.csv" for booking in bookings}
    with published_inputs(paths.values(), {}) as edition:
        for booking, name in paths.items():
            raw = (edition / name).read_bytes()
            reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
            if tuple(reader.fieldnames or ()) != FIELDS[booking]:
                parser.error(f"{name} has a different column layout from its issued desk statement")
            rows = [row for row in reader if row["shift"] == str(args.shift)]
            print(json.dumps({"booking": booking, "shift": args.shift, "ledger": name,
                              "sha256": sha256(raw).hexdigest(), "rows": rows}, ensure_ascii=False))


if __name__ == "__main__":
    main()
