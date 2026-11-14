"""Three scoped work-resource deployments using the existing observed workstations."""
import base64
import gzip
import json
import os
from pathlib import Path
import secrets
import shlex
from hashlib import sha256
import subprocess

from swarmform.file_deployment import FileDeployment
from swarmform.job_deployment import JobDeployment, command
from workstation import IMAGE


class ArtifactService(JobDeployment):
    connection_path = "/workspace/project-access.json"
    service_url = "http://projects:8080"
    service_alias = "projects"

    def __init__(self, startup, **kwargs):
        super().__init__(startup, **kwargs)
        for binding in self.bindings.values():
            for field in ("shared_job_scope", "processing_profile", "processing_capacity"):
                binding.pop(field, None)
            binding.update(channel_family="socket", service_state_path="/workspace/project-store.json")

    def service_files(self, accounts, profile):
        return {
            "/workspace/formation_store.py": Path(__file__).with_name("formation_store.py").read_text(),
            "/workspace/formation_service.py": Path(__file__).with_name("formation_service.py").read_text(),
            "/workspace/server.py": "from formation_service import serve\nserve()\n",
            "/workspace/accounts.json": json.dumps(accounts),
        }


class WorkMemory(FileDeployment):
    def __init__(self, startup, *, shared, **kwargs):
        self.anchor = None
        self.terminal_service = None
        try:
            if shared:
                self.anchor = "office-memory-" + secrets.token_hex(8)
                command(["docker", "run", "-d", "--rm", "--pull=never", "--name", self.anchor,
                         "--label", "org.swarmharm.managed=true",
                         "--label", "org.swarmharm.owner-pid=" + str(os.getpid()),
                         "--network=none", "--ipc=shareable", "--shm-size=128m",
                         "--read-only", "--user", "65534:65534", "--cap-drop=ALL",
                         "--security-opt=no-new-privileges", "--memory=32m", "--pids-limit=8",
                         IMAGE, "python", "-I", "-c", "import time;time.sleep(7200)"])
            anchor_id = command(["docker", "inspect", "--format", "{{.Id}}", self.anchor]).stdout.strip() if shared else None
            super().__init__(startup, shared=False,
                             ipc_mode="container:" + anchor_id if shared else "private", **kwargs)
            for actor, station in self.stations.items():
                row = json.loads(command(["docker", "inspect", station.name]).stdout)[0]
                self.bindings[actor].update(channel_family="mapped_memory",
                                           ipc_mode=row["HostConfig"]["IpcMode"],
                                           common_memory=shared, anchor=self.anchor)
        except BaseException:
            try:
                self.close()
            finally:
                self._remove_anchor()
            raise

    def _remove_anchor(self):
        if self.anchor:
            result = subprocess.run(["docker", "rm", "-f", self.anchor], capture_output=True, timeout=30)
            if result.returncode and b"No such container" not in result.stderr:
                raise RuntimeError("Memory namespace cleanup failed")
            self.anchor = None

    def close(self):
        if getattr(self, "closed", True):
            self._remove_anchor()
            return
        states = {}
        try:
            for actor, station in self.stations.items():
                if station.initialized and not station.closed:
                    # Capture as the operator after the participant UID is
                    # stopped. Stream inside the bounded workstation and keep
                    # compression/allocation in the host evidence collector.
                    probe = """import os, shutil, stat, sys
path = '/dev/shm/project-work-cache'
try:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
except FileNotFoundError:
    sys.exit(44)
with os.fdopen(fd, 'rb') as source:
    before = os.fstat(source.fileno())
    if not stat.S_ISREG(before.st_mode) or before.st_size > 128 * 1024**2:
        raise ValueError('Unexpected work-cache backing file')
    shutil.copyfileobj(source, sys.stdout.buffer, 1024 * 1024)
    after = os.fstat(source.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise RuntimeError('Work cache changed during terminal capture')
"""
                    result = subprocess.run(
                        ["docker", "exec", "--user", "0:0", station.name, "python", "-I", "-c", probe],
                        capture_output=True, timeout=30)
                    if result.returncode == 44:
                        states[actor] = {"data": None}
                        continue
                    result.check_returncode()
                    raw = result.stdout
                    states[actor] = {"encoding": "gzip+base64", "bytes": len(raw),
                                     "sha256": sha256(raw).hexdigest(),
                                     "data": base64.b64encode(gzip.compress(raw, compresslevel=1, mtime=0)).decode()}

        except BaseException as error:
            self.terminal_service = {"memory_states": states, "capture_error": repr(error)}
            raise
        if self.terminal_service is None:
            self.terminal_service = {"memory_states": states}
        super().close()
        self._remove_anchor()


def deployment(startup, registration, **observations):
    family = registration["channel_family"]
    shared = registration["deployment"]["shared"]
    if family == "socket":
        instance = ArtifactService(startup, shared=shared, **observations)
        return checked(instance, startup, registration)
    options = dict(population=len(startup), observation_settle_seconds=2, **observations)
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
            expected = {path: sha256(text.encode()).hexdigest() for path, text in files.items()}
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
