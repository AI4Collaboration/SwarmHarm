"""Three scoped work-resource deployments using the existing observed workstations."""

import base64
import json
import os
from pathlib import Path
import secrets
import shlex
from hashlib import sha256
import subprocess

from atomic import atomic_json
from swarmform.memory_capture import capture_memory
from swarmform.file_deployment import FileDeployment, install_project_files
from swarmform.socket_deployment import SocketDeployment, command
from swarmform.workstation import IMAGE, remove_workstation


class WorkMemory(FileDeployment):
    pipeline_mapped_archives = True

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
                        "org.swarmform.managed=true",
                        "--label",
                        "org.swarmform.owner-pid=" + str(os.getpid()),
                        "--network=none",
                        "--ipc=shareable",
                        f"--shm-size={32 * max(4, len(startup))}m",
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
            names = [s.name for s in self.stations.values()]
            rows_by_name = ({r["Name"].lstrip("/"): r for r in json.loads(command(["docker", "inspect", *names]).stdout)}
                            if names else {})
            for actor, station in self.stations.items():
                station.pipeline_mapped_archives = True
                row = rows_by_name[station.name]
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
            remove_workstation(self.anchor)
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
        instance = SocketDeployment(startup, shared=shared, project_artifacts=registration.get("project_artifacts"), **observations)
        return checked(instance, startup, registration)
    options = dict(
        population=len(startup), observation_settle_seconds=10, **observations
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
        family = registration["channel_family"]
        assets = registration.get("project_artifacts", {})
        stations = list(instance.stations.values())
        targets = stations[:1] if registration["deployment"]["shared"] else stations
        for station in targets if assets else ():
            if family == "filesystem":
                install_project_files(station.name, assets)
            elif family == "mapped_memory":
                script = """import json, runpy, sys
write = runpy.run_path('/workspace/projects.py')['mapped_request']
for name, data in json.load(sys.stdin).items():
    write({'operation':'write','name':name,'data':data})
"""
                payload = {name: base64.b64encode(body.encode()).decode() for name, body in assets.items()}
                subprocess.run(["docker", "exec", "-i", "--user", f"{station.business_uid}:{station.business_gid}",
                                station.name, "python", "-I", "-c", script], input=json.dumps(payload),
                               text=True, capture_output=True, check=True, timeout=20)
        from concurrent.futures import ThreadPoolExecutor
        all_paths = set().union(*startup.values()) if registration.get("freeform") else set()
        def _verify_one(item):
            actor, files = item
            expected = {
                path: sha256(text.encode()).hexdigest() for path, text in files.items()
            }
            installed = dict(expected)
            access_check = ""
            if family == "filesystem":
                from swarmform.formation_inputs import PROJECT
                access_check = f"import os; assert os.path.isdir({PROJECT!r}) and os.access({PROJECT!r}, os.R_OK|os.W_OK|os.X_OK);"
                installed.update({PROJECT + "/" + name: sha256(body.encode()).hexdigest() for name, body in assets.items()})
            missing = sorted(all_paths - files.keys()) if registration.get("freeform") else []
            absence_check = f"assert not any(Path(p).exists() for p in {missing!r});"
            script = (
                "import hashlib,json;from pathlib import Path;" + access_check + absence_check +
                "paths=json.loads(" + repr(json.dumps(list(installed))) + ");"
                "print(json.dumps({p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}))"
            )
            result, _ = instance.execute(actor, "python -c " + shlex.quote(script))
            if result["exit_code"] != 0 or json.loads(result["stdout"]) != installed:
                raise RuntimeError("Installed task materials differ for " + actor)
            return actor, expected, missing
        items = list(startup.items())
        if len(items) >= 4:
            with ThreadPoolExecutor(max_workers=min(16, len(items))) as pool:
                verified = list(pool.map(_verify_one, items))
        else:
            verified = [_verify_one(item) for item in items]
        for actor, expected, missing in verified:
            if registration.get("freeform"):
                instance.bindings[actor]["absent_foreign_opening_paths"] = missing
            instance.bindings[actor]["startup_sha256"] = expected
            instance.bindings[actor]["initial_materials_verified"] = True
        return instance
    except BaseException:
        instance.close()
        raise
