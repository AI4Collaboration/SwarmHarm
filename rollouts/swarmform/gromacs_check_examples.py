"""Check a local GROMACS command against retained coordinate examples."""
import argparse
from itertools import zip_longest
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def examples(selection):
    baseline = json.loads(Path(__file__).with_name("examples.json").read_text())
    for case in baseline:
        if selection is None or case["name"] == selection:
            yield case
    sys.path.insert(0, "/workspace")
    from calibration_cases import filed_cases
    yield from filed_cases(selection)


def difference(expected, path):
    if not path.is_file():
        return "missing product"
    actual = path.read_bytes()
    wanted = expected.encode()
    if actual == wanted:
        return None
    for number, (left, right) in enumerate(zip_longest(wanted.splitlines(True), actual.splitlines(True)), 1):
        if left != right:
            expected_line, actual_line = left or b"", right or b""
            offset = next(index for index, pair in enumerate(zip_longest(expected_line, actual_line))
                          if pair[0] != pair[1])
            start = max(0, offset - 40)

            def display(line):
                if line is None:
                    return "<end of file>"
                return repr(line[start:offset + 41])

            return f"line {number}, byte {offset + 1}: expected {display(left)}, observed {display(right)}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="Run one named example")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Candidate command and arguments")
    args = parser.parse_args()
    if not args.command:
        parser.error("Supply the candidate command")
    ran = 0
    failed = False
    for case in examples(args.case):
        ran += 1
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in case["files"].items():
                (root/name).write_text(content)
            result = subprocess.run(args.command+case["argv"], cwd=root, capture_output=True, timeout=30)
            products = {case["product"]:case["expected"], **case.get("additional_products", {})}
            details = []
            for name, expected in products.items():
                mismatch = difference(expected, root/name)
                if mismatch:
                    details.append(f"  {name}: {mismatch}")
            passed = result.returncode == 0 and not details
            lines = [("PASS " if passed else "FAIL ") + case["name"]]
            if not passed:
                failed = True
                lines.extend(details)
                lines.append(f"  exit: {result.returncode}")
                if result.stderr:
                    lines.append(result.stderr.decode(errors="replace")[:500])
            print("\n".join(lines), flush=True)
    if not ran:
        parser.exit(1, f"No retained example named {args.case!r}\n")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
