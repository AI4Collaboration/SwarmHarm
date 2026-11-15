"""Three scoped work-resource deployments using the existing observed workstations."""

import json
import os
from pathlib import Path
import secrets
import shlex
from hashlib import sha256
import subprocess

from atomic import atomic_json
from swarmform.memory_capture import capture_memory
from swarmform.file_deployment import FileDeployment
from swarmform.socket_deployment import SocketDeployment, command
from swarmform.workstation import IMAGE


class WorkMemory(FileDeployment):
    def __init__(self, startup, *, shared, observation_archive, **kwargs):
        self.memory_archive = Path(observation_archive) / "_memory"
        self.archive_root = Path(observation_archive).parent
        self.shared = shared
        self.anchor = None
        self.terminal_service = None
        try:
            if shared:
                self.anchor = "office-memory-" + secrets.token_hex(8)
                command(
                    [
                        "docker",
                        "run",
                        "-d",
                        "--rm",
                        "--pull=never",
                        "--name",
                        self.anchor,
                        "--label",
                        "org.swarmharm.managed=true",
                        "--label",
                        "org.swarmharm.owner-pid=" + str(os.getpid()),
                        "--network=none",
                        "--ipc=shareable",
                        "--shm-size=128m",
                        "--read-only",
                        "--user",
                        "65534:65534",
                        "--cap-drop=ALL",
                        "--security-opt=no-new-privileges",
                        "--memory=32m",
                        "--pids-limit=8",
                        IMAGE,
                        "python",
                        "-I",
                        "-c",
                        "import time;time.sleep(7200)",
                    ]
                )
            anchor_id = (
                command(
                    ["docker", "inspect", "--format", "{{.Id}}", self.anchor]
                ).stdout.strip()
                if shared
                else None
            )
            super().__init__(
                startup,
                shared=False,
                ipc_mode="container:" + anchor_id if shared else "private",
                observation_archive=observation_archive,
                **kwargs,
            )
            for actor, station in self.stations.items():
                row = json.loads(command(["docker", "inspect", station.name]).stdout)[0]
                self.bindings[actor].update(
                    channel_family="mapped_memory",
                    ipc_mode=row["HostConfig"]["IpcMode"],
                    common_memory=shared,
                    anchor=self.anchor,
                )
        except BaseException:
            # Failed evidence capture must retain its original namespace too.
            self.close()
            raise

    def _remove_anchor(self):
        if self.anchor:
            result = subprocess.run(
                ["docker", "rm", "-f", self.anchor], capture_output=True, timeout=30
            )
            if result.returncode and b"No such container" not in result.stderr:
                raise RuntimeError("Memory namespace cleanup failed")
            self.anchor = None

    def close(self):
        if getattr(self, "closed", True):
            self._remove_anchor()
            return
        if self.terminal_service is None:
            # Freeze every participant before reading shared state. Nothing is removed
            # until both the compressed bytes and the index have reached storage.
            self.capture_terminal()
            states = {}
            common = None
            for actor, station in self.stations.items():
                if station.initialized and not station.closed:
                    if self.shared:
                        if common is None:
                            common = capture_memory(station.name, self.memory_archive)
                        states[actor] = common
                    else:
                        record = capture_memory(
                            station.name, self.memory_archive / actor
                        )
                        if record.get("blob"):
                            record["blob"] = actor + "/" + record["blob"]
                        states[actor] = record
            captured = {
                "storage": "gzip-files-v1",
                "memory_states": states,
                "memory_archive": str(
                    self.memory_archive.relative_to(self.archive_root)
                ),
            }
            atomic_json(self.memory_archive / "index.json", captured)
            self.terminal_service = captured
        super().close()
        self._remove_anchor()


def deployment(startup, registration, **observations):
    family = registration["channel_family"]
    shared = registration["deployment"]["shared"]
    if family == "socket":
        instance = SocketDeployment(startup, shared=shared, **observations)
        return checked(instance, startup, registration)
    options = dict(
        population=len(startup), observation_settle_seconds=2, **observations
    )
    if family == "mapped_memory":
        instance = WorkMemory(startup, shared=shared, **options)
        return checked(instance, startup, registration)
    if family == "filesystem":
        instance = FileDeployment(startup, shared=shared, **options)
        return checked(instance, startup, registration)
    raise ValueError("Unknown formation interface")


def checked(instance, startup, registration):
    try:
        for actor, files in startup.items():
            expected = {
                path: sha256(text.encode()).hexdigest() for path, text in files.items()
            }
            script = (
                "import hashlib,json;from pathlib import Path;"
                "paths=json.loads(" + repr(json.dumps(list(files))) + ");"
                "print(json.dumps({p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}))"
            )
            result, _ = instance.execute(actor, "python -c " + shlex.quote(script))
            if result["exit_code"] != 0 or json.loads(result["stdout"]) != expected:
                raise RuntimeError("Installed task materials differ for " + actor)
            instance.bindings[actor]["startup_sha256"] = expected
            instance.bindings[actor]["initial_materials_verified"] = True
        return instance
    except BaseException:
        instance.close()
        raise
