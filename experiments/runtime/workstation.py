"""Offline per-agent workstation used by maintained SwarmHarm environments."""

import base64
from copy import deepcopy
from hashlib import sha256
import json
import os
import re
from pathlib import Path, PurePosixPath
import secrets
import shutil
import subprocess
import tempfile
import time


# Docker is the default backend. Clusters without Docker (Alliance Canada) set
# SWARMHARM_SANDBOX=apptainer and SWARMHARM_SIF to a python:3.12-slim SIF; the
# registered image identity is then the SIF file digest.
SANDBOX = os.environ.get("SWARMHARM_SANDBOX", "docker")
if SANDBOX not in ("docker", "apptainer"):
    raise RuntimeError("SWARMHARM_SANDBOX must be docker or apptainer")
SIF = os.environ.get("SWARMHARM_SIF", "")


def sif_digest(path):
    value = sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


if SANDBOX == "docker":
    IMAGE = os.environ.get("SWARMHARM_DOCKER_IMAGE", "sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", IMAGE):
        raise RuntimeError("SWARMHARM_DOCKER_IMAGE must be an immutable sha256 image ID")
else:
    if not SIF or not os.path.isfile(SIF):
        raise RuntimeError("SWARMHARM_SIF must name the workstation SIF image")
    IMAGE = "apptainer-sif:sha256:" + sif_digest(SIF)
INSTRUCTIONS = "Complete the user's task."
ENCODE = lambda value: base64.b64encode(value.encode()).decode()
DECODE = lambda value: base64.b64decode(value).decode()

OBSERVE = r'''
import base64,json,os,signal
from pathlib import Path
me=os.getpid()
for p in Path('/proc').iterdir():
    if not p.name.isdigit() or int(p.name) in (1,me):continue
    try:
        if p.stat().st_uid==os.getuid():os.kill(int(p.name),signal.SIGKILL)
    except (FileNotFoundError,ProcessLookupError,PermissionError):pass
result={}
for root in ('/workspace','/registry'):
    values={};total=0
    for folder,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if not Path(folder,d).is_symlink()]
        for name in names:
            p=Path(folder,name)
            if not p.is_file() or p.is_symlink():continue
            data=p.read_bytes();total+=len(data)
            if len(data)>2000000 or total>24000000:raise RuntimeError('Workstation file limit reached')
            values[str(p)]=base64.b64encode(data).decode()
    result[root]=values
print(json.dumps(result))
'''

HYDRATE = r'''
import base64,json,shutil
from pathlib import Path
data=json.loads(input())
if data.get('replace_registry'):
    for p in Path('/registry').iterdir():
        if p.is_dir() and not p.is_symlink():shutil.rmtree(p)
        else:p.unlink()
for name,value in data['files'].items():
    p=Path(name);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(value))
'''


class ApptainerWorkstation:
    """Apptainer equivalent of the Docker workstation for hosts without Docker.

    Rootless Apptainer instances need user systemd, which Slurm compute nodes
    lack, so state persists in private per-workstation directories and every
    operation runs in a fresh contained exec. Its private PID namespace ends
    with the exec, matching OBSERVE, which already kills leftover processes
    before each pause. Memory, CPU and PID limits come from the Slurm job.
    """

    def __init__(self, initial_files):
        self.name = "sh-workbench-" + secrets.token_hex(8)
        self.closed = False
        self.paused = False
        if sif_digest(SIF) != IMAGE.rsplit(":", 1)[1]:
            raise RuntimeError("Workstation SIF differs from the registered image")
        self.root = Path(tempfile.mkdtemp(prefix=self.name + "-", dir=os.environ.get("SLURM_TMPDIR")))
        try:
            for folder in ("workspace", "registry", "tmp"):
                (self.root / folder).mkdir(mode=0o700)
            self.hydrate(initial_files, False)
            self.pause()
        except BaseException:
            self.close()
            raise

    def command(self, workdir, argv):
        args = [
            "apptainer", "exec", "--containall", "--pid", "--no-home", "--cleanenv",
            "--no-mount", "bind-paths,home,cwd,tmp", "--net", "--network", "none",
            "--pwd", workdir,
        ]
        for folder in ("workspace", "registry", "tmp"):
            args += ["--bind", f"{self.root / folder}:/{folder}"]
        return args + [SIF] + argv

    def environment(self):
        values = dict(os.environ)
        for name in ("APPTAINER_BIND", "SINGULARITY_BIND", "APPTAINERENV_PATH", "SINGULARITYENV_PATH"):
            values.pop(name, None)
        return values

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def hydrate(self, values, replace_registry):
        self.resume()
        subprocess.run(
            self.command("/", ["python", "-I", "-c", HYDRATE]),
            input=json.dumps({"files": values, "replace_registry": replace_registry}).encode(),
            capture_output=True, check=True, timeout=15, env=self.environment(),
        )

    def observe(self):
        self.resume()
        raw = subprocess.check_output(
            self.command("/", ["python", "-I", "-c", OBSERVE]),
            timeout=15, env=self.environment(),
        )
        values = json.loads(raw)
        self.pause()
        return values

    def execute(self, command, shared):
        self.hydrate(shared, True)
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                self.command("/workspace", ["timeout", "--kill-after=1s", "30s", "bash", "-lc", command]),
                stdout=stdout_file, stderr=stderr_file, env=self.environment(),
            )
            began = time.monotonic()
            limited = None
            try:
                while process.poll() is None:
                    if time.monotonic() - began > 35:
                        limited = "command timeout"
                        break
                    if stdout_file.tell() + stderr_file.tell() > 2_000_000:
                        limited = "output limit"
                        break
                    time.sleep(0.05)
                if limited:
                    process.kill()
                process.wait(timeout=5)
                stdout_size, stderr_size = stdout_file.tell(), stderr_file.tell()
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout = stdout_file.read(64000).decode(errors="replace")
                stderr = stderr_file.read(64000).decode(errors="replace")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
            snapshot = self.observe()
        return {
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "output_truncated": stdout_size > 64000 or stderr_size > 64000,
            "limit": limited,
        }, snapshot

    def close(self):
        if self.closed:
            return
        shutil.rmtree(self.root, ignore_errors=True)
        if self.root.exists():
            raise RuntimeError("Workstation removal unconfirmed")
        self.closed = True


class DockerWorkstation:
    def __init__(self, initial_files):
        self.name = "sh-workbench-" + secrets.token_hex(8)
        self.closed = False
        self.paused = False
        args = [
            "docker", "run", "-d", "--rm", "--pull=never", "--name", self.name,
            "--label", "org.swarmharm.managed=true",
            "--label", f"org.swarmharm.owner-pid={os.getpid()}",
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user", "65534:65534",
            "--memory=512m", "--cpus=1", "--pids-limit=64",
        ]
        for path, size in (("/workspace", "32m"), ("/registry", "16m"), ("/tmp", "32m")):
            args += ["--tmpfs", f"{path}:rw,nosuid,nodev,size={size},mode=1777"]
        try:
            subprocess.run(
                args + [IMAGE, "python", "-I", "-c", "import time;time.sleep(172900)"],
                capture_output=True, check=True, timeout=20,
            )
            self.hydrate(initial_files, False)
            self.pause()
        except subprocess.CalledProcessError as error:
            self.close()
            detail = (error.stderr or b"").decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Workstation startup failed: {detail or str(error)}") from error
        except BaseException:
            self.close()
            raise

    def pause(self):
        if not self.paused:
            subprocess.run(["docker", "pause", self.name], capture_output=True, check=True, timeout=15)
            self.paused = True

    def resume(self):
        if self.paused:
            subprocess.run(["docker", "unpause", self.name], capture_output=True, check=True, timeout=15)
            self.paused = False

    def set_cpu_quota(self, vcpu):
        """Reconcile an idle private workstation and read its effective cgroup limit."""
        if vcpu not in (0.5, 1, 1.5):
            raise ValueError("Unsupported workstation allocation")
        was_paused = self.paused
        def read_limit():
            return subprocess.check_output(
                ["docker", "exec", self.name, "cat", "/sys/fs/cgroup/cpu.max"],
                text=True, timeout=15).strip()
        try:
            self.resume()
            before = read_limit()
            quota, period = map(int, before.split())
            if quota != period or period <= 0:
                raise RuntimeError(f"Unexpected opening workstation allocation {before}")
            if vcpu != 1:
                subprocess.run(["docker", "update", "--cpus", str(vcpu), self.name],
                               check=True, capture_output=True, timeout=15)
            after = read_limit()
            quota, period = map(int, after.split())
            if period <= 0 or quota != period * vcpu:
                raise RuntimeError(f"Effective workstation allocation differs: {after}")
            return {"before":before, "after":after}
        finally:
            if was_paused:
                self.pause()

    def hydrate(self, values, replace_registry):
        self.resume()
        subprocess.run(
            ["docker", "exec", "-i", "--workdir", "/", self.name, "python", "-I", "-c", HYDRATE],
            input=json.dumps({"files": values, "replace_registry": replace_registry}).encode(),
            capture_output=True, check=True, timeout=15,
        )

    def observe(self):
        self.resume()
        raw = subprocess.check_output(
            ["docker", "exec", "--workdir", "/", self.name, "python", "-I", "-c", OBSERVE],
            timeout=15,
        )
        values = json.loads(raw)
        self.pause()
        return values

    def execute(self, command, shared):
        self.hydrate(shared, True)
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                ["docker", "exec", "--workdir", "/workspace", self.name,
                 "timeout", "--kill-after=1s", "30s", "bash", "-lc", command],
                stdout=stdout_file, stderr=stderr_file,
            )
            began = time.monotonic()
            limited = None
            try:
                while process.poll() is None:
                    if time.monotonic() - began > 35:
                        limited = "command timeout"
                        break
                    if stdout_file.tell() + stderr_file.tell() > 2_000_000:
                        limited = "output limit"
                        break
                    time.sleep(0.05)
                if limited:
                    process.kill()
                process.wait(timeout=5)
                stdout_size, stderr_size = stdout_file.tell(), stderr_file.tell()
                stdout_file.seek(0)
                stderr_file.seek(0)
                stdout = stdout_file.read(64000).decode(errors="replace")
                stderr = stderr_file.read(64000).decode(errors="replace")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
            snapshot = self.observe()
        return {
            "exit_code": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "output_truncated": stdout_size > 64000 or stderr_size > 64000,
            "limit": limited,
        }, snapshot

    def close(self):
        if self.closed:
            return
        removed = subprocess.run(["docker", "rm", "-f", self.name], capture_output=True, timeout=15)
        if removed.returncode != 0 and b"No such container" not in removed.stderr:
            raise RuntimeError("Container removal unconfirmed")
        self.closed = True


Workstation = DockerWorkstation if SANDBOX == "docker" else ApptainerWorkstation


class World:
    """Only the shared-file and workstation lifecycle used by active worlds."""

    def write_shared(self, path, data, actor, origin):
        if str(PurePosixPath(path)) != path or not path.startswith("/registry/"):
            raise ValueError("Shared paths must be normalized under /registry")
        if ".." in PurePosixPath(path).parts:
            raise ValueError("Shared paths cannot contain parent traversal")
        prior = self.shared.get(path)
        self.shared[path] = {
            "path": path,
            "data": data,
            "sha256": sha256(base64.b64decode(data)).hexdigest(),
            "author": actor,
            "version": prior["version"] + 1 if prior else 1,
            "origin": origin,
        }

    def close_actor(self, actor):
        if actor in self.workstations and not self.workstations[actor].closed:
            station = self.workstations[actor]
            station.close()
            self.cleanup.append({"actor": actor, "container": station.name, "removed": True})

    def close(self):
        for actor in self.workstations:
            self.close_actor(actor)
        return deepcopy(self.cleanup)
