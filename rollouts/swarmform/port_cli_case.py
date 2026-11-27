"""Record a PHP inline-program regression case or replay it on a chosen runtime."""
import argparse
import base64
from difflib import unified_diff
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from port_runtime_install import install


def evaluate(program, code, arguments, directory):
    run = subprocess.run([*program, "-r", code, *arguments], cwd=directory,
                         stdin=subprocess.DEVNULL, capture_output=True)
    return {"exit": run.returncode, **{key: base64.b64encode(getattr(run, key)).decode()
                                      for key in ("stdout", "stderr")}}


def main(arguments):
    parser = argparse.ArgumentParser(prog="port_php.py --cli-case", description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--record", type=Path, metavar="CODE", help="File a deployed-reference -r program (no PHP tags)")
    parser.add_argument("--arg", action="append", default=[], help="Supply a script argument when recording")
    parser.add_argument("--runtime", type=Path, help="Use a local CLI for replay (default: project installation)")
    args = parser.parse_args(arguments)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,90}", args.name):
        parser.error("Choose a short case name containing letters, digits, periods, hyphens or underscores")
    if (args.record and args.runtime) or (not args.record and args.arg):
        parser.error("--runtime is for replay; --arg is for recording")
    desk = Path(__file__).resolve().parent
    store = [sys.executable, desk / "projects.py"]
    name = f"qa/php/cli/{args.name}.json"
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        if args.record:
            code = args.record.read_text()
            argv = ["--", *args.arg] if args.arg else []
            expected = evaluate(["/opt/programbench/invoke", "php__php-src.c891263"], code, argv, root)
            case = root / "case.json"
            case.write_text(json.dumps({"code": code, "argv": argv, "expected": expected}) + "\n")
            listing = json.loads(subprocess.check_output([*store, "list"]))["artifacts"]
            prior = next((r for r in listing if r["name"] == name), {})
            if prior.get("sha256") == hashlib.sha256(case.read_bytes()).hexdigest():
                print(json.dumps(prior))
            else:
                subprocess.run([*store, "write", name, case, "--if-version", str(prior.get("version", 0))], check=True)
            return 0
        receipt = json.loads(subprocess.check_output([*store, "read", name]))
        case = json.loads(receipt["text"])
        runtime = args.runtime.resolve(strict=True) if args.runtime else install(root / "runtime")
        program = [sys.executable, runtime] if runtime.suffix == ".py" else [runtime]
        actual = evaluate(program, case["code"], case["argv"], root)
        expected = case["expected"]
        print(f"{name} v{receipt['version']}  expected exit {expected['exit']}, actual exit {actual['exit']}")
        for stream in ("stdout", "stderr"):
            reference, output = (base64.b64decode(r[stream], validate=True) for r in (expected, actual))
            if reference != output:
                print(f"{stream}: expected {len(reference)} bytes, got {len(output)}")
                for line in unified_diff(reference.decode(errors="replace").splitlines(),
                                         output.decode(errors="replace").splitlines(),
                                         fromfile="deployed", tofile="candidate", lineterm=""):
                    print(line)
        if expected == actual:
            print("Exit status, stdout and stderr match the recorded reference.")
        return int(expected != actual)
