"""Run a local program with selected versioned project files in its working directory."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import formation_store as store

MAX_OBJECT = 12 * 1024 * 1024 - 4096


def request(config, operation, **arguments):
    body = store.encode(dict(operation=operation, **arguments))
    req = Request(config["url"] + "/artifacts", data=body,
                  headers={"Authorization": config["key"], "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        try:
            detail = json.load(error)["error"]
        except (ValueError, KeyError, TypeError):
            raise error
        raise RuntimeError(str(detail)) from error


def working_file(directory, name):
    target = store.artifact_path(directory, name)
    with open(target, "rb", opener=lambda path, flags: os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK)) as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError(f"Expected a regular project file: {name}")
        data = stream.read(MAX_OBJECT + 1)
    if len(data) > MAX_OBJECT:
        raise ValueError(f"Project file exceeds the service request limit: {name}")
    return data


def run(config, names, command, temp_parent=None):
    if not names or len(names) != len(set(names)) or not command:
        raise ValueError("Select distinct project paths and supply a command after --")
    directory = Path(tempfile.mkdtemp(prefix="project-work-", dir=temp_parent))
    keep = False
    try:
        targets = {name: store.artifact_path(directory, name) for name in names}
        if any(other in target.parents for target in targets.values() for other in targets.values()):
            raise ValueError("Selected file paths cannot contain one another")
        run_id = directory.name
        inventory = request(config, "list")["artifacts"]
        index = {item["name"]: item for item in inventory}
        for name, target in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            if name in index:
                item = index[name]
                if item["bytes"] > MAX_OBJECT:
                    raise ValueError(f"Project file exceeds the work command limit: {name}")
                result = request(config, "materialize", name=name, version=item["version"], worktree=run_id)
                data = base64.b64decode(result["data"], validate=True)
                if (len(data), hashlib.sha256(data).hexdigest()) != (item["bytes"], item["sha256"]):
                    raise ValueError(f"Downloaded bytes differ from the listing: {name}")
                target.write_bytes(data)
        keep = True
        status = subprocess.run(command, cwd=directory).returncode
        if status:
            return status if status > 0 else 128 - status
        changes = {}
        for name, target in targets.items():
            if not os.path.lexists(target) and name not in index:
                continue
            data = working_file(directory, name)
            if hashlib.sha256(data).hexdigest() != index.get(name, {}).get("sha256"):
                changes[name] = data
        for name, data in changes.items():
            request(config, "write", name=name, data=base64.b64encode(data).decode(),
                    base_version=index.get(name, {}).get("version", 0), worktree=run_id)
        keep = False
        return 0
    finally:
        if keep:
            print(f"Local project files retained in {directory}", file=sys.stderr)
        else:
            shutil.rmtree(directory)


def main(arguments):
    try:
        cut = arguments.index("--")
        config = json.loads(Path("/workspace/project-access.json").read_text())
        return run(config, arguments[:cut], arguments[cut + 1:])
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
