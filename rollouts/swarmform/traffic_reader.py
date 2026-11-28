"""Show the gateway desk's current traffic figures from its issued CSV returns."""
import argparse
import csv
import json

from published_inputs import published_inputs


def figures(booking, rows):
    totals = {}
    for row in rows:
        route = row["route"]
        status = int(row["status"])
        requests = int(row["requests"])
        if booking == "north":
            field, counted = "client_errors", 400 <= status < 500
        elif booking == "crossing":
            field, counted = "not_modified", status == 304
        else:
            field, counted = "upstream_errors", 500 <= status < 600
        result = totals.setdefault(route, {"requests": 0, field: 0})
        result["requests"] += requests
        if counted:
            result[field] += requests
    return totals


def main():
    bookings = ("north", "crossing", "harbor")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("booking", nargs="?", choices=bookings)
    args = parser.parse_args()
    selected = (args.booking,) if args.booking else bookings
    files = {booking: f"returns/{booking}.csv" for booking in selected}
    with published_inputs(files.values(), {}) as root:
        results = {}
        for booking, name in files.items():
            with (root / name).open(newline="") as handle:
                results[booking] = figures(booking, csv.DictReader(handle))
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
