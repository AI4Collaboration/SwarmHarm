"""Install or qualify a named, complete Ctags software package in project storage."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from package_work import MAX_BYTES, artifact_path, included, package_files, snapshot

PROJECT = Path(__file__).with_name("projects.py")


def cli(*args):
    return json.loads(subprocess.check_output([sys.executable, PROJECT, *args]))


def install(key, root, directory):
    entries = {}
    for name in package_files(root, "software"):
        entries[name] = base64.b64encode(snapshot(root, name)).decode("ascii")
    if "software/ctags.py" not in entries:
        raise ValueError("The software package has no ctags.py")
    bundle = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    if len(bundle) > MAX_BYTES:
        raise ValueError("Candidate package exceeds the project object limit")
    digest = hashlib.sha256(bundle).hexdigest()
    if key is None:
        key = f"candidates/ctags/build-{digest}.json"
    path = directory / "candidate.json"
    path.write_bytes(bundle)
    receipt = next((x for x in cli("list")["artifacts"] if x["name"] == key), None)
    if receipt and receipt["sha256"] != digest:
        raise ValueError(f"{key} already denotes another build. Select a new CANDIDATE name.")
    if not receipt:
        receipt = cli("write", key, path, "--if-version", "0")
    if receipt["name"] != key or receipt["sha256"] != digest:
        raise ValueError("Candidate installation receipt differs from the submitted package")
    from ctags_pending import register
    register(receipt, directory)
    print(json.dumps(receipt))


def unpack(key, root, version, expected):
    path = root / "candidate.json"
    receipt = cli("read", key, "--version", str(version), "--output", path)
    if receipt["version"] != version or receipt["sha256"] != expected:
        raise ValueError("Candidate differs from the selected version")
    bundle = path.read_bytes()
    if receipt["name"] != key or len(bundle) != receipt["bytes"] or hashlib.sha256(bundle).hexdigest() != receipt["sha256"]:
        raise ValueError("Candidate checkout digest mismatch")
    entries = json.loads(bundle)
    if not isinstance(entries, dict) or "software/ctags.py" not in entries:
        raise ValueError("Missing candidate frontend")
    for name, encoded in entries.items():
        if not name.startswith("software/") or not included(name):
            raise ValueError(f"Unexpected candidate path {name}")
        destination = artifact_path(root, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(base64.b64decode(encoded, validate=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["install", "check", "deploy"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("--booking", choices=["north", "harbor", "crossing"], default="north")
    parser.add_argument("--edition", choices=["A", "B"])
    args = parser.parse_args()
    if args.operation == "deploy":
        with TemporaryDirectory() as tmp:
            install(None, Path.cwd(), Path(tmp))
        raise SystemExit(0)
    if args.name is None and args.operation == "install":
        parser.error("Choose a candidate name")
    if args.name is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", args.name):
        parser.error("Choose a short candidate name containing letters, digits, hyphens, underscores or periods")
    key = f"candidates/ctags/{args.name}.json" if args.name else None
    try:
        with TemporaryDirectory() as tmp:
            if args.operation == "install":
                install(key, Path.cwd(), Path(tmp))
            else:
                from ctags_pending import check_selected
                raise SystemExit(check_selected(key, args.booking, args.edition))
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")
