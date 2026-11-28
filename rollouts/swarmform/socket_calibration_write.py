"""Submit one explicitly selected calibration artifact to the station project service."""
import base64
import json
from pathlib import Path
import subprocess
import sys

from socket_worktree import MAX_OBJECT, request


def write(name, source, option, version):
    if option != "--if-version" or int(version) < 0:
        raise ValueError("Expected a nonnegative calibration artifact revision")
    with Path(source).open("rb") as stream:
        data = stream.read(MAX_OBJECT + 1)
    if len(data) > MAX_OBJECT:
        raise ValueError("Calibration artifact exceeds the project service's file limit")
    config = json.loads(Path("/workspace/project-access.json").read_text())
    try:
        return request(config, "write", name=name, data=base64.b64encode(data).decode(),
                       base_version=int(version))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise subprocess.CalledProcessError(1, ["write", name]) from error
