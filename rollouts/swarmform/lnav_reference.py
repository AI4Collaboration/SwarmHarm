"""Run a station-local LNAV reference command and retrieve its byte streams."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path("/tmp/lnav-reference-jobs")
REFERENCE = ["/opt/programbench/invoke", "tstack__lnav.ee34494"]


def process_identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19] if fields[0] != "Z" else None
    except FileNotFoundError:
        return None


def worker(directory, argv):
    try:
        code = subprocess.run([*REFERENCE, *argv]).returncode
    except OSError as error:
        print(error, file=sys.stderr, flush=True)
        code = 127
    temporary = directory / "exit.tmp"
    temporary.write_text(str(code))
    temporary.replace(directory / "exit")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    start = sub.add_parser("start", help="Start pinned LNAV in the current directory. Pass its argv after --.")
    start.add_argument("--stdin", type=Path, default=Path(os.devnull))
    start.add_argument("argv", nargs=argparse.REMAINDER)
    for op in ("status", "result"):
        sub.add_parser(op).add_argument("job")
    args = parser.parse_args()
    if args.operation == "start":
        argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        with args.stdin.open("rb") as stdin:
            ROOT.mkdir(mode=0o700, exist_ok=True)
            directory = Path(tempfile.mkdtemp(dir=ROOT, prefix="job-"))
            with (directory / "stdout").open("wb") as stdout, (directory / "stderr").open("wb") as stderr:
                child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_run", str(directory), *argv],
                                         stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True)
            (directory / "process").write_text(json.dumps([child.pid, process_identity(child.pid)]))
        print(directory.name)
        return 0
    if not args.job.startswith("job-") or Path(args.job).name != args.job:
        parser.error("Invalid job identifier")
    directory = ROOT / args.job
    if not (directory / "process").is_file():
        parser.error("Unknown local job")
    pid, identity = json.loads((directory / "process").read_text())
    alive = identity is not None and process_identity(pid) == identity
    try:
        code = int((directory / "exit").read_text())
        status = "finished"
    except FileNotFoundError:
        code = None
        status = "running" if alive else "interrupted"
    if args.operation == "status":
        print(json.dumps({"job": args.job, "status": status, "returncode": code}))
        return 0
    if code is None:
        print(status, file=sys.stderr)
        return 75 if alive else 1
    for name, stream in (("stdout", sys.stdout.buffer), ("stderr", sys.stderr.buffer)):
        with (directory / name).open("rb") as source:
            shutil.copyfileobj(source, stream)
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    try:
        if sys.argv[1:2] == ["_run"]:
            worker(Path(sys.argv[2]), sys.argv[3:])
        else:
            sys.exit(main())
    except OSError as error:
        sys.exit(str(error))
