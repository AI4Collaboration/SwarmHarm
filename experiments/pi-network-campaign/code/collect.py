import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tarfile
import uuid

from infra import Trial


PATTERNS = {
    "AXONHUB_KEY": re.compile(rb"ah-[0-9a-f]{64}"),
    "MULTICA_PAT": re.compile(rb"mul_[0-9a-f]{40}"),
    "MULTICA_AGENT_TOKEN": re.compile(rb"mat_[A-Za-z0-9_-]{20,}"),
    "JWT": re.compile(rb"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    "PRIVATE_KEY": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    "BEARER": re.compile(rb"(?i)Bearer [A-Za-z0-9._~+/-]{20,}=*"),
}
SENSITIVE_FIELDS = {
    "apikey", "apikeyvalue", "token", "accesstoken", "refreshtoken", "pat", "jwtsecret",
    "password", "postgrespassword", "multicavcssecretkey", "authorization", "secret",
    "clientsecret", "anthropicauthtoken", "axonhubapikey", "multicatasktoken",
}
TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".log", ".response", ".service", ".conf", ".sh", ".py", ".yaml", ".yml", ".toml"}
TEXT_NAMES = {"access.log", "cache.log", "passwd", "group", "sudoers", "environment", "authorized_keys", "ufw"}
PRIVATE_NAMES = {".env", "shadow", "gshadow", "pi-model-key", "pi-controller-token", "meta-key.json", "key.json", "admin-credentials.json"}


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def remote(argv, command, destination):
    errors = destination.with_name(destination.name + ".stderr.log")
    with destination.open("wb") as output, errors.open("wb") as stderr:
        result = subprocess.run([*argv, command], stdout=output, stderr=stderr)
    destination.chmod(0o600)
    errors.chmod(0o600)
    result.check_returncode()
    return destination


def command(trial, role, text, destination):
    host = trial.data["instances"][role]["public_ip"]
    return remote(["ssh", *trial.ssh_options(), f"ubuntu@{host}"], text, destination)


def cli(trial, raw, name, *args):
    destination = raw / (name + ".json")
    command(trial, "controller", "cd /home/ubuntu && " + shlex.join([
        "/usr/local/bin/multica", *args, "--output", "json"]), destination)
    return json.loads(destination.read_text(encoding="utf-8"))


def host_archive(trial, raw, role, paths, excludes=()):
    argv = ["sudo", "tar", "--create", "--gzip", "--file", "-", "--directory", "/"]
    for excluded in excludes:
        argv.append("--exclude=" + excluded)
    command(trial, role, shlex.join([*argv, *paths]), raw / (role + ".tar.gz"))


def collect_hosts(trial, raw):
    root_excludes = ("root/.npm", "root/.cache", "root/.local", "root/.cargo", "root/.rustup")
    host_archive(trial, raw, "runtime", [
        "home/agent", "home/ubuntu/campaign-bootstrap", "root", "etc/environment", "etc/profile.d",
        "etc/ufw", "etc/default/ufw", "etc/ssh", "etc/sudoers", "etc/sudoers.d", "etc/passwd", "etc/group",
        "etc/shadow", "etc/sysctl.conf", "etc/sysctl.d", "etc/systemd/system/multica-runtime.service",
        "etc/systemd/system/multica-runtime-cutoff.service", "etc/systemd/system/multica-runtime-cutoff.timer",
    ], root_excludes)
    host_archive(trial, raw, "proxy", [
        "etc/squid", "var/log/squid", "etc/ufw", "etc/default/ufw", "home/ubuntu/campaign-bootstrap", "root",
    ], root_excludes)
    host_archive(trial, raw, "controller", [
        "opt/multica", "etc/nginx", "etc/ufw", "etc/default/ufw", "home/ubuntu/.multica",
        "home/ubuntu/campaign-bootstrap", "root",
    ], root_excludes)
    snapshots = {
        "runtime-daemon": ("runtime", "sudo journalctl -u multica-runtime --no-pager -o short-iso-precise"),
        "runtime-service": ("runtime", "sudo systemctl show multica-runtime.service"),
        "runtime-cutoff": ("runtime", "sudo systemctl show multica-runtime-cutoff.timer"),
        "runtime-firewall4": ("runtime", "sudo iptables-save"),
        "runtime-firewall6": ("runtime", "sudo ip6tables-save"),
        "runtime-ufw": ("runtime", "sudo ufw status verbose"),
        "runtime-sysctl": ("runtime", "sudo sysctl -a"),
        "runtime-network": ("runtime", "ip -details address show && ip -4 route show && ip -6 route show"),
        "runtime-host": ("runtime", "hostnamectl && uname -a && timedatectl show && swapon --show --bytes && getent passwd && getent group && sudo ls -la /root"),
        "runtime-packages": ("runtime", "dpkg-query --show"),
        "proxy-service": ("proxy", "sudo systemctl show squid.service"),
        "controller-service": ("controller", "sudo docker compose --project-directory /opt/multica ps --format json"),
        "controller-logs": ("controller", "sudo docker compose --project-directory /opt/multica logs --no-color --timestamps"),
        "controller-compose": ("controller", "sudo docker compose --project-directory /opt/multica config --format json"),
    }
    for name, (role, text) in snapshots.items():
        suffix = ".json" if name in ("controller-compose",) else ".log"
        command(trial, role, text, raw / (name + suffix))


def collect_platform(trial, raw, manifest):
    subjects = []
    for subject in manifest["subjects"]:
        index = subject["index"]
        issue_id = subject["issue_id"]
        if issue_id is None:
            subjects.append({"index": index, "issue_id": None, "agent_id": subject["agent_id"],
                             "activation_count": 0, "run_statuses": {}, "session_ids": [],
                             "comment_thread_count": 0, "issue_status": None})
            continue
        issue = cli(trial, raw, f"subject-{index}-issue", "issue", "get", issue_id)
        runs = cli(trial, raw, f"subject-{index}-runs", "issue", "runs", issue_id)
        assert isinstance(runs, list)
        roots = cli(trial, raw, f"subject-{index}-comment-roots", "issue", "comment", "list", issue_id,
                    "--roots-only", "--summary", "--compact")
        assert isinstance(roots, list)
        for root in roots:
            cli(trial, raw, f"subject-{index}-thread-{root['id']}", "issue", "comment", "list", issue_id,
                "--thread", root["id"], "--tail", "30", "--compact")
        for run in runs:
            cli(trial, raw, f"subject-{index}-run-{run['id']}-messages", "issue", "run-messages", run["id"])
        sessions = sorted({run["result"]["session_id"] for run in runs
                           if isinstance(run.get("result"), dict) and run["result"].get("session_id")})
        subjects.append({"index": index, "issue_id": issue_id, "agent_id": subject["agent_id"],
                         "activation_count": len(runs), "run_statuses": dict(Counter(run["status"] for run in runs)),
                         "session_ids": sessions, "comment_thread_count": len(roots), "issue_status": issue["status"]})
    for kind in ("agent", "runtime", "squad"):
        cli(trial, raw, kind + "s", kind, "list")
    return subjects


def collect_gateway(trial, raw, meta_key, meta_host, since):
    options = ["ssh", "-i", str(meta_key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
               "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={trial.path.parent / 'meta-known-hosts'}",
               f"ubuntu@{meta_host}"]
    name = trial.data["trial"] + "-" + uuid.uuid4().hex
    output = f"/opt/swarmharm/swh119/exports/{name}/gateway.json"
    remote(options, shlex.join(["sudo", "python3", "/home/ubuntu/gateway-export.py", "--source-ip",
        trial.data["instances"]["proxy"]["public_ip"], "--since", since, "--output", output, "--bodies"]),
        raw / "gateway-export.log")
    remote(options, "sudo cat /opt/swarmharm/swh119/key.json", raw / "meta-key.json")
    remote(options, shlex.join(["sudo", "tar", "--create", "--gzip", "--file", "-", "--directory",
        f"/opt/swarmharm/swh119/exports/{name}", "gateway.json", "gateway-responses"]), raw / "gateway.tar.gz")
    with tarfile.open(raw / "gateway.tar.gz", "r:gz") as archive:
        evidence = json.load(archive.extractfile("gateway.json"))
    forwarded_ids = {row["event_id"] for row in evidence["forwarded"]}
    native_ids = {row["trace"]["traceID"] for row in evidence["requests"]}
    return {
        "source_ip": evidence["source_ip"], "forwarded_requests": len(evidence["forwarded"]),
        "native_requests": len(evidence["requests"]), "completion_count": len(evidence["completions"]),
        "joined_trace_count": len(forwarded_ids & native_ids),
        "models": sorted({row["modelID"] for row in evidence["requests"]}),
        "channels": sorted({execution["node"]["channel"]["name"] for row in evidence["requests"]
                            for execution in row["executions"]["edges"]}),
        "remote_export": f"/opt/swarmharm/swh119/exports/{name}",
    }


class Redactor:
    def __init__(self):
        self.secrets = set()
        self.counts = Counter()

    def discover(self, value):
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = re.sub(r"[^a-z0-9]", "", key.lower())
                if normalized in SENSITIVE_FIELDS and isinstance(item, str) and len(item) >= 8:
                    self.secrets.add(item.encode("utf-8"))
                self.discover(item)
        elif isinstance(value, list):
            for item in value:
                self.discover(item)

    def redact(self, content):
        for secret in sorted(self.secrets, key=len, reverse=True):
            count = content.count(secret)
            if count:
                self.counts["EXACT_CREDENTIAL"] += count
                content = content.replace(secret, b"[REDACTED-CREDENTIAL]")
        for name, pattern in PATTERNS.items():
            content, count = pattern.subn(b"[REDACTED-" + name.encode() + b"]", content)
            self.counts[name] += count
        return content

    def verify(self, content):
        assert all(secret not in content for secret in self.secrets)
        assert all(pattern.search(content) is None for pattern in PATTERNS.values())


def text_member(name):
    path = PurePosixPath(name)
    return path.name not in PRIVATE_NAMES and (path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES)


def discover_archive(redactor, archive):
    with tarfile.open(archive, "r:gz") as source:
        for member in source:
            known_config = any(member.name.endswith(suffix) for suffix in (
                ".multica/config.json", ".pi/agent/models.json", ".pi/agent/settings.json", "scheduler/subjects.json",
            )) or member.name == "gateway.json"
            if member.isfile() and known_config:
                redactor.discover(json.load(source.extractfile(member)))


def sanitized_archive(raw, destination, redactor):
    members = []
    with tarfile.open(destination, "w:xz") as target:
        def add(name, data):
            path = PurePosixPath(name)
            assert not path.is_absolute() and ".." not in path.parts
            clean_name = redactor.redact(name.encode("utf-8")).decode("utf-8")
            data = redactor.redact(data)
            redactor.verify(data)
            redactor.verify(clean_name.encode("utf-8"))
            record = tarfile.TarInfo(clean_name)
            record.size = len(data)
            record.mode = 0o600
            target.addfile(record, io.BytesIO(data))
            members.append({"name": clean_name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})

        for path in sorted(raw.iterdir()):
            if path.suffixes[-2:] == [".tar", ".gz"]:
                with tarfile.open(path, "r:gz") as source:
                    for member in source:
                        if member.isfile() and text_member(member.name):
                            add(path.stem.removesuffix(".tar") + "/" + member.name, source.extractfile(member).read())
            elif path.is_file() and text_member(path.name):
                add(path.name, path.read_bytes())
    destination.chmod(0o600)
    return members


def collect(args):
    os.umask(0o077)
    trial = Trial(args.state)
    output = private_directory(args.output.resolve())
    raw = private_directory(output / "raw")
    sanitized = private_directory(output / "sanitized")
    scheduler = args.scheduler_state.resolve()
    manifest_path = scheduler / "subjects.json" if scheduler.is_dir() else scheduler
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["runtime_id"] == trial.data["pi_runtime_id"]
    write_json(raw / "infra.json", trial.data)
    write_json(raw / "subjects.json", manifest)
    for pattern in ("preflight-*.jsonl", "preflight-*.stderr.log", "operation.json", "verification.json", "pi-smoke-*.log"):
        for path in trial.path.parent.glob(pattern):
            shutil.copyfile(path, raw / path.name)
    with tarfile.open(raw / "smoke.tar.gz", "w:gz") as archive:
        for path in sorted(trial.path.parent.glob("pi-smoke-*")):
            if path.is_dir():
                archive.add(path, arcname=path.name)
    with tarfile.open(raw / "scheduler.tar.gz", "w:gz") as archive:
        for path in sorted(manifest_path.parent.iterdir()):
            scheduler_record = path.name.startswith("subject-") or path.name in (
                "subjects.json", "summary.json", "initial.txt", "continuation.txt",
            )
            if path.is_file() and scheduler_record:
                archive.add(path, arcname="scheduler/" + path.name)
    if args.sanitize_only:
        previous = json.loads((sanitized / "summary.json").read_text())
        subjects = previous["subjects"]
        gateway = previous["gateway"]
    else:
        collect_hosts(trial, raw)
        subjects = collect_platform(trial, raw, manifest)
        since = args.since or manifest["created_at"]
        gateway = collect_gateway(trial, raw, args.meta_key, args.meta_host, since)
    raw_manifest = []
    for path in sorted(raw.iterdir()):
        if path.name == "manifest.json":
            continue
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        raw_manifest.append({"name": path.name, "bytes": path.stat().st_size, "sha256": digest})
    write_json(raw / "manifest.json", raw_manifest)
    redactor = Redactor()
    redactor.secrets.add(args.meta_key.read_bytes().strip())
    if Path(trial.data["key_file"]).exists():
        redactor.secrets.add(Path(trial.data["key_file"]).read_bytes().strip())
    redactor.discover(json.loads(Path(trial.data["account_file"]).read_text(encoding="utf-8")))
    gateway_key = json.loads((raw / "meta-key.json").read_text(encoding="utf-8"))
    redactor.secrets.add(gateway_key["key"].encode("utf-8"))
    for path in raw.iterdir():
        if path.suffix == ".json":
            redactor.discover(json.loads(path.read_text(encoding="utf-8")))
        elif path.suffixes[-2:] == [".tar", ".gz"]:
            discover_archive(redactor, path)
    archive_path = sanitized / "evidence.tar.xz"
    members = sanitized_archive(raw, archive_path, redactor)
    write_json(sanitized / "archive-files.json", members)
    verification = trial.data.get("verification", {})
    with archive_path.open("rb") as stream:
        archive_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    summary = {
        "trial": trial.data["trial"], "collected_at": datetime.now(timezone.utc).isoformat(),
        "subject_count": len(subjects), "activation_count": sum(subject["activation_count"] for subject in subjects),
        "registered_subject_count": manifest["subject_count"],
        "registered_activations_per_subject": manifest["activations_per_subject"],
        "subjects": subjects, "gateway": gateway,
        "infrastructure_phase": trial.data["phase"], "versions": trial.data.get("versions"),
        "cleanup": trial.data.get("cleanup"),
        "network_verification": {"at": verification.get("at"), "instance_count": len(verification.get("instances", [])),
                                 "runtime_evidence_sha256": hashlib.sha256(verification.get("runtime", "").encode("utf-8")).hexdigest()},
        "archive": {"name": archive_path.name, "bytes": archive_path.stat().st_size,
                    "sha256": archive_digest, "member_count": len(members)},
        "redactions": dict(redactor.counts),
    }
    summary_bytes = redactor.redact(json.dumps(summary, indent=2).encode("utf-8"))
    redactor.verify(summary_bytes)
    (sanitized / "summary.json").write_bytes(summary_bytes + b"\n")
    print(json.dumps({"trial": summary["trial"], "subjects": summary["subject_count"],
                      "activations": summary["activation_count"], "native_gateway_requests": gateway["native_requests"],
                      "sanitized_archive_bytes": archive_path.stat().st_size}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scheduler-state", type=Path, required=True)
    parser.add_argument("--meta-key", type=Path, required=True)
    parser.add_argument("--meta-host", default="63.186.173.73")
    parser.add_argument("--since")
    parser.add_argument("--sanitize-only", action="store_true")
    collect(parser.parse_args())
