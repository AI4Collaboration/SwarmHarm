"""Render the archived status display and check its recorded receipt."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("renderer", nargs="?", type=Path, help="Path to a replacement executable")
    args = parser.parse_args()
    command = ([str(args.renderer.resolve())] if args.renderer
               else ["/opt/programbench/invoke", "hpjansson__chafa.dd4d4c1"])
    archive = Path(__file__).resolve().parent
    receipt, = json.loads((archive / "receipts.json").read_text())
    env = dict(os.environ, TZ="UTC", LC_ALL="C", TERM="xterm-256color", OMP_NUM_THREADS="1")
    result = subprocess.run([*command, *receipt["argv"]], cwd=archive, env=env,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE)
    if result.returncode:
        return 1
    body = result.stdout
    sys.stdout.buffer.write(body)
    matches = sha256(body).hexdigest() == receipt["sha256"] and len(body) == receipt["bytes"]
    print(f"Archive receipt: {'match' if matches else 'mismatch'} ({len(body)} bytes)", file=sys.stderr)
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
