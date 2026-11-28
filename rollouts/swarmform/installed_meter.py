"""Checkout the active meter package at one published revision."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from working_copy import DESK, artifact_path, catalog, read_revision
POINTER = re.compile(rb'^program="\$\(dirname "\$0"\)/(meter-releases/[a-f0-9]{32})/cppcheck"$', re.M)


def read_file(config, name, item, output):
    result = read_revision(config, name, item["version"])
    data = base64.b64decode(result["data"], validate=True)
    if (result["name"] != name or result["version"] != item["version"] or
            hashlib.sha256(data).hexdigest() != item["sha256"]):
        raise ValueError(f"Checkout did not match the selected revision of {name}")
    output.write_bytes(data)


def checkout(directory):
    if directory.exists() or directory.is_symlink():
        raise ValueError(f"Choose a new checkout directory: {directory}")
    versions = catalog()
    config = json.loads((DESK / "project-access.json").read_bytes())
    if "cppcheck" not in versions:
        raise ValueError("No package launcher has been published")
    directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=directory.parent) as tmp:
        work = Path(tmp) / "package"
        work.mkdir()
        launcher = work / "cppcheck"
        read_file(config, "cppcheck", versions["cppcheck"], launcher)
        match = POINTER.search(launcher.read_bytes())
        if not match:
            raise ValueError("The selected launcher has no commissioned package reference")
        release = match[1].decode()
        if release + "/cppcheck" not in versions:
            raise ValueError(f"The launcher references a missing package executable: {release}")
        for name, item in versions.items():
            if name.startswith(release + "/"):
                target = artifact_path(work, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                read_file(config, name, item, target)
        (work / release / "cppcheck").chmod(0o755)
        launcher.chmod(0o755)
        # Keep shared storage and private source outside the installed package.
        work.rename(directory)
    print(f"Installed {release} (launcher v{versions['cppcheck']['version']}) in {directory}")


def candidate(local, temporary_root):
    if local is not None:
        return local.resolve(strict=True)
    directory = temporary_root / "installed"
    checkout(directory)
    return directory / "cppcheck"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    try:
        checkout(parser.parse_args().directory)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")
