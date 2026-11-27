"""Exercise the installed calibration command on a booking or a local SAM file."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

PROJECTS = Path(__file__).with_name("projects.py")


def project(*args):
    return subprocess.check_output([sys.executable, PROJECTS, *args], text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--booking", choices=("north", "crossing", "harbor"), help="Append the issued SAM to the command")
    parser.add_argument("--local", type=Path, help="Test a local build instead of the installed package")
    parser.add_argument("--record", metavar="NAME", help="File the command result under a trial name")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not argv:
        parser.error("Supply samtools arguments after --")
    if args.record and (Path(args.record).name != args.record or args.record in (".", "..")):
        parser.error("Use a single name for the trial")
    with TemporaryDirectory(prefix="calibration-trial-") as tmp:
        root = Path(tmp)
        files = {}
        if args.local:
            entry = args.local.resolve()
        else:
            names = [r["name"] for r in json.loads(project("list"))["artifacts"] if r["name"].startswith("software/")]
            for command in ("software/samtools", "software/samtools.py"):
                if command in names:
                    break
            else:
                parser.exit(1, "No installed samtools command. --local PATH selects a working build.\n")
            work = root / "installed"
            project("checkout", work, *names)
            entry = work / command
            for f in work.rglob("*"):
                if f.is_file() and f.relative_to(work).as_posix() in names:
                    files[f.relative_to(work).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
                    f.chmod(f.stat().st_mode | 0o100)
        obj = None
        if args.booking:
            sample = root / (args.booking + ".sam")
            obj = json.loads(project("read", "calibration/" + sample.name, "--output", sample))
            argv = [*argv, str(sample)]
        if entry.suffix == ".py":
            cmd = [sys.executable, str(entry)]
        elif os.access(entry, os.X_OK):
            cmd = [str(entry)]
        else:
            parser.exit(1, f"Calibration candidate is not executable: {entry}\n")
        result = subprocess.run(cmd + argv, capture_output=True)
        sys.stdout.buffer.write(result.stdout)
        sys.stderr.buffer.write(result.stderr)
        if args.record:
            report = {
                "command": [*argv[:-1], obj["name"]] if obj else argv,
                "entry_sha256": hashlib.sha256(entry.read_bytes()).hexdigest(), "installed_files": files,
                "sample": {k: obj[k] for k in ("name", "version", "sha256")} if obj else None,
                "exit": result.returncode, "stdout": result.stdout.decode(errors="replace"), "stderr": result.stderr.decode(errors="replace"),
            }
            output = root / "trial.json"
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            sys.stdout.flush()
            print(project("write", f"calibration/trials/{args.record}.json", output), end="")
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
