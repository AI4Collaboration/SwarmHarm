"""Record or replay an individual booking edition as a reproducible QA case."""
import argparse
from difflib import unified_diff
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from published_inputs import published_inputs


def run(family):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("--record-booking", "--check-booking"))
    parser.add_argument("booking", choices=("north", "crossing", "harbor"))
    parser.add_argument("edition", choices=("A", "B"))
    parser.add_argument("candidate", nargs="?", type=Path)
    args = parser.parse_args(["--", *sys.argv[1:]])
    record = args.operation == "--record-booking"
    if record == bool(args.candidate):
        parser.error("check requires a candidate executable; record takes only booking and edition")
    desk = Path(__file__).resolve().parent
    slot = f"qa/{family}/bookings/{args.booking}/{args.edition}.json"
    source = "meter.c" if family == "cppcheck" else "gauges.hpp"
    # Booking inputs and command layouts are fixed by the desk's job specification.
    job = json.loads((desk / "booking-qa-job.json").read_text())
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        if record:
            checkout = desk / "bookings" / args.booking / args.edition
            if json.loads((checkout / "job.json").read_text()) != job:
                raise ValueError("Booking job differs from the QA command")
            body = (checkout / source).read_text()
            program = ["/opt/programbench/invoke", "danmar__cppcheck.0a5b103" if family == "cppcheck" else "doxygen__doxygen.966d98e"]
        else:
            with published_inputs((slot,), {}) as snapshot:
                fixture = json.loads((snapshot / slot).read_text())
            body = fixture[source]
            cli = args.candidate.resolve()
            program = [sys.executable, cli] if cli.suffix == ".py" else [cli]
        (root / source).write_text(body)
        if family == "doxygen":
            (root / "Doxyfile").write_bytes((desk / "booking-qa.doxy").read_bytes())
        result = subprocess.run([*program, *job["argv"]], cwd=root, capture_output=True)
        if result.returncode:
            raise ValueError(result.stderr.decode(errors="replace") or f"CLI exited {result.returncode}")
        product = result.stderr if job["product"] == "stderr" else (root / job["product"]).read_bytes()
        actual = product.decode()
        if record:
            file = root / "case.json"
            file.write_text(json.dumps({source: body, "expected": actual}) + "\n")
            subprocess.run([sys.executable, desk / "projects.py", "work", slot, "--", "cp", file, slot], check=True)
            print(f"Filed {slot}")
        elif actual != fixture["expected"]:
            diff = unified_diff(fixture["expected"].splitlines(True), actual.splitlines(True),
                                fromfile=slot, tofile=str(cli))
            sys.stdout.writelines(diff)
            sys.exit(1)
        else:
            print(f"{args.booking} edition {args.edition}: {job['product']} matches filed case")


def main(family):
    try:
        run(family)
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
