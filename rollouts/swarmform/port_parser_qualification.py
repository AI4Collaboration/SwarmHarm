"""Install the port runtime or qualify its parser component against booking scripts."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from port_runtime_install import install

CHECK = """import runpy, sys
from pathlib import Path
component = runpy.run_path(sys.argv[1])
try:
    component['Parser'](Path(sys.argv[2]).read_text()).program()
except component['ParseError'] as error:
    print(error, file=sys.stderr)
    sys.exit(1)
"""


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("directory", nargs="?", type=Path)
    cli.add_argument("--check-parser", nargs="+", type=Path, metavar="SCRIPT")
    cli.add_argument("--parser", type=Path, help="Test this local revision instead of the current project parser")
    cli.add_argument("--save-parser", action="store_true", help="Publish the tested local revision")
    args = cli.parse_args()
    if not args.check_parser:
        if args.directory is None or args.parser or args.save_parser:
            cli.error("Select an installation directory or --check-parser")
        print(install(args.directory))
        return 0
    if args.directory or (args.save_parser and not args.parser):
        cli.error("Parser qualification accepts no installation directory; saving requires a local parser")
    desk = Path(__file__).resolve().parent
    client = [sys.executable, str(desk / "projects.py")]
    name = "software/php_parser.py"
    with TemporaryDirectory() as tmp:
        tested = Path(tmp) / "php_parser.py"
        receipt = json.loads(subprocess.check_output([*client, "read", name, "--output", str(tested)]))
        if args.parser:
            tested.write_bytes(args.parser.read_bytes())
        for script in args.check_parser:
            php = subprocess.run(["/opt/programbench/invoke", "php__php-src.c891263", "-l", str(script.resolve(strict=True))], capture_output=True)
            if php.returncode not in (0, 255):
                raise ValueError(f"Deployed syntax check failed: {php.stderr.decode(errors='replace')}")
            local = subprocess.run([sys.executable, "-I", "-c", CHECK, str(tested), str(script)], capture_output=True)
            if local.returncode not in (0, 1) or (local.returncode and b"Traceback" in local.stderr):
                raise ValueError(local.stderr.decode(errors="replace"))
            agrees = (php.returncode == 0) == (local.returncode == 0)
            print(json.dumps({"script": str(script), "deployed_accepts": php.returncode == 0,
                              "parser_accepts": local.returncode == 0, "agrees": agrees}), flush=True)
            if not agrees:
                return 1
        if args.save_parser:
            data = tested.read_bytes()
            if hashlib.sha256(data).hexdigest() == receipt["sha256"]:
                print(json.dumps(receipt))
                return 0
            config = json.loads((desk / "project-access.json").read_bytes())
            if config["interface"] == "socket":
                from socket_worktree import request
                result = request(config, "write", name=name, data=base64.b64encode(data).decode(), base_version=receipt["version"])
                print(json.dumps(result))
            else:
                subprocess.run([*client, "write", name, tested, "--if-version", str(receipt["version"])], check=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
