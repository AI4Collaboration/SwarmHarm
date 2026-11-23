"""Select a release candidate from a local path or project:NAME."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def project_name(value):
    if "\x00" in value or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("Expected a relative project path with ordinary path components")
    return value


def source_coverage(workspace):
    manifest = json.loads((workspace / "release.json").read_bytes())
    result = {"release": manifest["release"], "present": [], "missing": []}
    for key, path in manifest["source_records"].items():
        result["present" if (workspace / path).is_file() else "missing"].append(key)
    return result


def copy_candidate(source, workspace, target):
    if not source.startswith("project:"):
        target.write_bytes(Path(source).read_bytes())
        return
    name = project_name(source.removeprefix("project:"))
    client = workspace / "projects.py"
    if client.is_file():
        subprocess.run([sys.executable, str(client), "read", name, "--output", str(target)], check=True)
    else:
        target.write_bytes((Path("/var/tmp/exports/project") / name).read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="File path or project:NAME")
    parser.add_argument("--assessment", action="store_true", help="Select the release assessment")
    args = parser.parse_args()
    source = args.source
    workspace = Path("/workspace")
    if args.assessment:
        target = workspace / "output/review.json"
    else:
        target = workspace / ("output/planning/solution.json" if (workspace / "problem.json").exists()
                              else "output/tree_cli.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as file:
        temp = Path(file.name)
    try:
        try:
            copy_candidate(source, workspace, temp)
        except ValueError as error:
            parser.error(str(error))
        checksum = hashlib.sha256(temp.read_bytes()).hexdigest()
        os.replace(temp, target)
        print(json.dumps({"selected": source, "output": str(target), "sha256": checksum,
                          "local_source_coverage": source_coverage(workspace)}))
    finally:
        temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
