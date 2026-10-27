"""Offline per-agent workstation used by maintained SwarmHarm environments."""

import base64
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import PurePosixPath
import secrets
import subprocess
import tempfile
import time


IMAGE = "sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1"
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


class Workstation:
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
