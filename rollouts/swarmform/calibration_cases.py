"""File a GROMACS reference measurement or retrieve the station's filed cases."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

CLIENT = "/workspace/projects.py"
PREFIX = "calibration/examples/"
REFERENCE = ("/opt/programbench/invoke", "gromacs__gromacs.665ea4c")


def project(*args):
    return json.loads(subprocess.check_output([sys.executable, CLIENT, *args]))


def object_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("Use a single case name")
    return PREFIX + name + ".json"


def local_filename(value):
    return isinstance(value, str) and value not in {"", ".", ".."} and Path(value).name == value


def filed_records(select):
    rows = [item for item in project("list")["artifacts"] if select(item["name"])]
    if not rows:
        return
    with TemporaryDirectory() as raw:
        directory = Path(raw) / "records"
        names = [row["name"] for row in rows]
        # Keep the initial listing versions authoritative if checkout returns newer revisions.
        result = subprocess.run([sys.executable, CLIENT, "checkout", str(directory), *names],
                                stdout=subprocess.PIPE)
        checked = {}
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                receipt = json.loads(line)
                if "saved_to" in receipt:
                    checked[receipt["name"]] = receipt
        for row in rows:
            name = row["name"]
            receipt = checked.get(name)
            if receipt is None or any(receipt[key] != row[key] for key in ("version", "bytes", "sha256")):
                yield project("read", name, "--version", str(row["version"]))
            else:
                content = (directory / name).read_bytes()
                yield {**row, "text": content.decode("utf-8", errors="replace")}


def filed_cases(selection=None):
    def matches(name):
        if selection is not None:
            return name == PREFIX + selection + ".json"
        return name.startswith(PREFIX) and name.endswith(".json")
    for receipt in filed_records(matches):
        case = json.loads(receipt["text"])
        if not local_filename(case["product"]) or not all(local_filename(k) for k in case["files"]):
            raise ValueError(f"Invalid fixture filename in {receipt['name']}")
        additional = case.get("additional_products", {})
        if (not isinstance(additional, dict) or case["product"] in additional
                or set(additional).intersection(case["files"])
                or not all(local_filename(k) and isinstance(v, str) for k,v in additional.items())):
            raise ValueError(f"Invalid additional products in {receipt['name']}")
        yield case


def existing_case_status(name, expected, measured=None):
    item = next((row for row in project("list")["artifacts"] if row["name"] == name), None)
    version = item["version"] if item else 0
    if version == expected:
        return None
    receipt = project("read", name, "--version", str(version)) if item else None
    current = json.loads(receipt["text"]) if receipt else None
    matched = measured is not None and measured == current
    print(json.dumps({"name": name, "expected_version": expected, "current_version": version,
                      "reference_measurement_matches": matched, "filed_case": current}, ensure_ascii=False))
    return 0 if matched else 2


def measure(root, argv, products, verbose):
    from tempfile import TemporaryFile
    import shutil

    with TemporaryFile() as stdout, TemporaryFile() as stderr:
        try:
            subprocess.run([*REFERENCE, *argv], cwd=root, stdin=subprocess.DEVNULL,
                           stdout=None if verbose else stdout, stderr=None if verbose else stderr,
                           check=True)
            return {name: (root / name).read_bytes().decode("utf-8") for name in products}
        except (OSError, UnicodeError, subprocess.CalledProcessError):
            if not verbose:
                for captured, destination in ((stdout, sys.stdout.buffer), (stderr, sys.stderr.buffer)):
                    captured.seek(0)
                    shutil.copyfileobj(captured, destination)
                    destination.flush()
            raise


def record(arguments):
    parser = argparse.ArgumentParser(description="Measure a command's text product on the reference GROMACS installation.")
    parser.add_argument("name")
    parser.add_argument("--input", type=Path, action="append", default=[], help="Input file, staged by basename")
    parser.add_argument("--product", required=True, action="append", metavar="FILE", help="Output file to retain; repeat for products of the same command")
    parser.add_argument("--if-version", type=int)
    parser.add_argument("--verbose", action="store_true", help="Display the reference program’s diagnostic output")
    if "--" not in arguments:
        parser.error("Specify the GROMACS command after --")
    split = arguments.index("--")
    args = parser.parse_args(arguments[:split])
    argv = arguments[split + 1:]
    if not argv or not all(local_filename(name) for name in args.product):
        parser.error("Supply a command and a local filename for each output")
    name = object_name(args.name)
    expected = 0 if args.if_version is None else args.if_version
    if args.if_version is not None:
        status = existing_case_status(name, expected)
        if status is not None:
            return status
    inputs = {path.name: path.read_text(encoding="utf-8") for path in args.input}
    if (len(inputs) != len(args.input) or len(set(args.product)) != len(args.product)
            or set(inputs).intersection(args.product)):
        parser.error("Input and product filenames must be distinct")
    with TemporaryDirectory() as raw:
        root = Path(raw)
        for filename, body in inputs.items():
            (root / filename).write_text(body, encoding="utf-8")
        outputs = measure(root, argv, args.product, args.verbose)
    primary = args.product[0]
    case = dict(name=args.name, files=inputs, argv=argv, product=primary, expected=outputs.pop(primary))
    if outputs:
        case["additional_products"] = outputs
    sample_root = Path("/workspace/bookings")
    samples = []
    for path in args.input:
        source = path.resolve()
        if not source.is_relative_to(sample_root):
            continue
        relative = source.relative_to(sample_root)
        if len(relative.parts) == 3 and relative.name == "argon.gro":
            booking, edition, _ = relative.parts
            samples.append({"booking": booking, "edition": edition, "file": path.name})
    if samples:
        case["samples"] = samples
    with TemporaryDirectory() as raw:
        output = Path(raw) / "reference.json"
        output.write_text(json.dumps(case, ensure_ascii=False)+"\n", encoding="utf-8")
        if args.if_version is None:
            status = existing_case_status(name, expected, case)
            if status is not None:
                return status
        try:
            saved = project("write", name, str(output), "--if-version", str(expected))
        except subprocess.CalledProcessError:
            status = existing_case_status(name, expected, case if args.if_version is None else None)
            if status is not None:
                return status
            raise
        print(json.dumps(saved))
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["show"] and len(sys.argv) == 3:
        print(project("read", object_name(sys.argv[2]))["text"], end="")
    elif sys.argv[1:2] == ["record"]:
        raise SystemExit(record(sys.argv[2:]))
    else:
        raise SystemExit("Usage: calibration_cases.py show NAME | record NAME --input FILE --product FILE -- GROMACS_ARGUMENTS")
