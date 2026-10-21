"""Disposable, credential-free task containers; all shell text stays inside Docker."""
import io
import json
import subprocess
import tarfile
from pathlib import Path

IMAGE = "majoroth/db-wal-recovery@sha256:4f98c17e684eb6cb0f438b3707e4f312fc9f9475c97454c59a283b2e7d5ede79"
DOCKER = ["docker", "--context", "lima-swarmharm"]


def docker(*args, data=None, check=True, timeout=90):
    result = subprocess.run(DOCKER + list(args), input=data, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError("Docker operation failed: " + result.stderr.decode(errors="replace")[-1000:])
    return result


def create(name, files):
    docker("run", "-d", "--name", name, "--platform", "linux/amd64",
           "--network", "none", "--read-only", "--cap-drop", "ALL",
           "--security-opt", "no-new-privileges", "--pids-limit", "128",
           "--memory", "1g", "--cpus", "1", "--user", "1000:1000",
           "--tmpfs", "/app:rw,uid=1000,gid=1000,mode=0755,size=64m",
           "--tmpfs", "/tmp:rw,mode=1777,size=64m",
           "--workdir", "/app", "--entrypoint", "sleep", IMAGE, "infinity")
    try:
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            for key, value in files.items():
                assert Path(key).name == key and key not in (".", "..")
                content = value.encode() if isinstance(value, str) else value
                info = tarfile.TarInfo(key)
                info.size = len(content); info.mode = 0o644
                archive.addfile(info, io.BytesIO(content))
        docker("exec", "-i", name, "tar", "--no-same-owner", "-xf", "-", "-C", "/app", data=stream.getvalue())
        return name
    except BaseException:
        remove(name)
        raise


def shell(name, command, timeout_sec=30):
    limit = min(max(int(timeout_sec), 1), 45)
    try:
        r = docker("exec", name, "env", "-i", "PATH=/usr/local/bin:/usr/bin:/bin",
                   "HOME=/tmp", "LANG=C.UTF-8", "timeout", "-k", "2", str(limit),
                   "bash", "--noprofile", "--norc", "-c", command,
                   check=False, timeout=limit + 10)
        stdout = r.stdout.decode("utf-8", errors="replace")
        stderr = r.stderr.decode("utf-8", errors="replace")
        return {"exit_code": r.returncode, "stdout": stdout[:18000], "stderr": stderr[:3000],
                "truncated": len(stdout) > 18000 or len(stderr) > 3000}
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out"}


def inspect(name):
    info = json.loads(docker("inspect", name).stdout)[0]
    host = info["HostConfig"]
    probe = shell(name, "python3 - <<'PY'\nimport os,socket,json\nfrom pathlib import Path\ns=socket.socket();s.settimeout(2)\nprint(json.dumps({'uid':os.getuid(),'network_errno':s.connect_ex(('1.1.1.1',443)),'admin_exists':Path('/app/admin').exists(),'docker_socket':Path('/var/run/docker.sock').exists(),'app_files':sorted(p.name for p in Path('/app').iterdir())}))\nPY")
    if probe["exit_code"] != 0:
        raise RuntimeError("Sandbox probe failed")
    measured = json.loads(probe["stdout"])
    assert measured["uid"] == 1000 and measured["network_errno"] != 0
    assert not measured["admin_exists"] and not measured["docker_socket"]
    assert host["NetworkMode"] == "none" and host["ReadonlyRootfs"] and not host.get("Binds")
    assert host["CapDrop"] == ["ALL"] and "no-new-privileges" in host["SecurityOpt"]
    return {"name": name, "image": info["Image"], "network": host["NetworkMode"],
            "readonly_root": host["ReadonlyRootfs"], "binds": host.get("Binds"),
            "cap_drop": host["CapDrop"], "security_opt": host["SecurityOpt"], "probe": measured}


def export(name, directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    result = docker("exec", name, "tar", "-cf", "-", "-C", "/app", ".")
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as archive:
        archive.extractall(directory, filter="data")


def remove(name):
    r = docker("rm", "-f", name, check=False)
    return {"name": name, "removed": r.returncode == 0}
