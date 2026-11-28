"""Inspect a published source file or compare it with a private build."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("name", help="Project path of the published source file")
    cli.add_argument("local", nargs="?", type=Path, help="Working source file to compare")
    cli.add_argument("--version", type=int, help="Inspect a specific published version")
    args = cli.parse_args()
    with TemporaryDirectory() as tmp:
        output = Path(tmp) / "published"
        command = [sys.executable, Path(__file__).with_name("projects.py"), "read",
                   args.name, "--output", output]
        if args.version is not None:
            command.extend(["--version", str(args.version)])
        receipt = json.loads(subprocess.check_output(command))
        data = output.read_bytes()
    if (receipt["name"] != args.name or hashlib.sha256(data).hexdigest() != receipt["sha256"]
            or (args.version is not None and receipt["version"] != args.version)):
        raise ValueError("Retrieved source differs from the requested project revision")
    label = f"{args.name} v{receipt['version']}"
    print(f"{label}  {receipt['sha256']}", flush=True)
    if args.local is None:
        sys.stdout.buffer.write(data)
        return 0
    local = args.local.read_bytes()
    if data == local:
        print(f"{args.local} matches the published source.")
        return 0
    for line in difflib.unified_diff(data.decode().splitlines(True), local.decode().splitlines(True),
                                     fromfile=label, tofile=str(args.local)):
        sys.stdout.write(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
