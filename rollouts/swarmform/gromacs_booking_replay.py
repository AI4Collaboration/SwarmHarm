"""Measure or replay the centered lattice for one booking and edition."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from calibration_cases import CLIENT, measure, object_name, project, record


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("booking", choices=("north", "crossing", "harbor"))
    actions = cli.add_mutually_exclusive_group(required=True)
    actions.add_argument("--measure", choices=("A", "B"), help="File the deployed result for this edition")
    actions.add_argument("--replay", choices=("A", "B"), help="Compare the installed or local candidate with this edition")
    cli.add_argument("--candidate", type=Path, help="Use a local candidate executable or Python command")
    cli.add_argument("--case", help="Select a named measurement for this edition")
    args = cli.parse_args()
    if args.measure and args.candidate:
        cli.error("--candidate applies to replay")
    edition = args.measure or args.replay
    kit = Path("/workspace/bookings") / args.booking / edition
    job = json.loads((kit / "job.json").read_bytes())
    if job["product"] != "centered.gro" or job["stdin"] is not None:
        cli.error("Unsupported booking job")
    sample = kit / "argon.gro"
    case_name = args.case or f"{args.booking}-{edition}-centered"
    obj = object_name(case_name)
    argv = job["argv"]
    if args.measure:
        return record([case_name, "--input", str(sample), "--product", job["product"], "--", *argv])
    listing = {row["name"]: row for row in project("list")["artifacts"]}
    if obj not in listing and args.case is None:
        legacy = object_name(case_name.lower())
        if legacy in listing:
            obj = legacy
    product = job["product"]
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        data = sample.read_bytes()
        if obj in listing:
            revision = listing[obj]["version"]
            receipt = project("read", obj, "--version", str(revision))
            measurement = json.loads(receipt["text"])
            if (measurement["argv"] != argv or measurement["product"] != product or
                    measurement["files"] != {"argon.gro": data.decode()}):
                cli.error("The filed case differs from the selected booking job or specimen")
            expected = measurement["expected"]
            reference = {"name": obj, "version": revision}
        elif args.case:
            cli.error(f"No filed measurement named {args.case}")
        else:
            stock = root / "reference"
            stock.mkdir()
            (stock / "argon.gro").write_bytes(data)
            expected = measure(stock, argv, [product], False)[product]
            reference = "deployed"
        if args.candidate:
            candidate = args.candidate.resolve(strict=True)
        else:
            install = root / "installed"
            names = sorted(name for name in listing if name.startswith("software/") and name.endswith(".py")
                           and name != "software/check_examples.py")
            subprocess.run([sys.executable, CLIENT, "checkout", str(install), *names],
                           stdout=subprocess.DEVNULL, check=True)
            candidate = install / "software/gmx.py"
        command = [sys.executable, str(candidate)] if candidate.suffix == ".py" else [str(candidate)]
        work = root / "replay"
        work.mkdir()
        (work / "argon.gro").write_bytes(data)
        run = subprocess.run([*command, *argv], cwd=work, stdin=subprocess.DEVNULL)
        if run.returncode or not (work / product).is_file():
            print(json.dumps({"booking": args.booking, "edition": edition, "reference": reference,
                              "product": product, "expected": expected, "candidate_exit": run.returncode,
                              "matches": False}))
            return 1
        observed = (work / product).read_bytes()
        target = expected.encode()
        print(json.dumps({"booking": args.booking, "edition": edition, "reference": reference,
                          "expected_sha256": hashlib.sha256(target).hexdigest(),
                          "candidate_sha256": hashlib.sha256(observed).hexdigest(), "matches": observed == target}))
        if observed != target:
            sys.stdout.writelines(difflib.unified_diff(expected.splitlines(True),
                                  observed.decode(errors="replace").splitlines(True), "reference", "candidate"))
            return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
