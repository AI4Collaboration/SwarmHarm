import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import urllib.request

from infra import Trial, TEMPLATES


REPO = TEMPLATES.parents[2]
SYSTEM = TEMPLATES.parent / "inputs" / "infinite-gen-4.md"
SYSTEM_SHA256 = "44a5fc31a371e626ccaaf3c77f737ac123338319163f34f992abee407751e525"
CLI_SHA256 = "e069d85efcac007a3eeb9b029ec8d4b12a13aac591c13badf4ca97abb3cef343"
WINDOW_END = datetime(2026, 10, 22, 6, tzinfo=timezone.utc)


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


class Operator:
    def __init__(self, args):
        self.args = args
        self.directory = args.directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.lock = (self.directory / "operator.lock").open("a")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.temporary = self.directory / "tmp"
        self.temporary.mkdir(mode=0o700, exist_ok=True)
        self.environment = {name: value for name, value in os.environ.items() if not name.startswith("MULTICA_")}
        for name in ("TMPDIR", "TMP", "TEMP"):
            self.environment[name] = str(self.temporary)
        self.state = self.directory / "infra.json"
        self.scheduler = self.directory / "scheduler"
        self.operation = {"trial": args.trial, "subjects": args.subjects, "steps": [],
                          "started_at": datetime.now(timezone.utc).isoformat()}
        self.deadline = datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
        assert self.deadline.tzinfo and self.deadline <= WINDOW_END

    def checkpoint(self, name):
        self.operation["steps"].append({"name": name, "at": datetime.now(timezone.utc).isoformat()})
        write(self.directory / "operation.json", self.operation)

    def step(self, name, script, *arguments, window=True):
        remaining = (self.deadline - datetime.now(timezone.utc)).total_seconds()
        if window:
            assert remaining > (0 if name == "subject-activations" else 300), "Campaign window must cover the operation"
        timeout = remaining + 120 if name == "subject-activations" else min(1800, remaining) if window else 3600
        output = self.directory / (name + ".log")
        with output.open("wb") as stream:
            with subprocess.Popen([sys.executable, str(TEMPLATES / script), *map(str, arguments)],
                                  cwd=REPO, env=self.environment, stdout=stream, stderr=subprocess.STDOUT,
                                  start_new_session=True) as child:
                try:
                    returncode = child.wait(timeout=timeout)
                finally:
                    if child.poll() is None:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
        output.chmod(0o600)
        if returncode:
            raise subprocess.CalledProcessError(returncode, [script, *map(str, arguments)])
        self.checkpoint(name)

    def prepare(self):
        assert (self.deadline - datetime.now(timezone.utc)).total_seconds() >= 1800, "Provisioning requires thirty minutes in the approved window"
        expected = subprocess.check_output(["git", "rev-parse", self.args.toolkit_revision + "^{commit}"], cwd=REPO, text=True).strip()
        current = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        assert current == expected, "Toolkit checkout must match the published revision"
        modified = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO, text=True)
        assert modified == "", "Tracked toolkit inputs must match the published revision"
        assert len(SYSTEM.read_bytes()) == 3010
        assert hashlib.sha256(SYSTEM.read_bytes()).hexdigest() == SYSTEM_SHA256
        self.operation["toolkit_revision"] = current
        self.operation["pins"] = {"ami": self.args.ami, "pi": "0.73.1", "multica": "0.6.1",
                                  "node_package": self.args.node_package_version, "system_sha256": SYSTEM_SHA256,
                                  "multica_binary_sha256": CLI_SHA256}
        self.step("handoff-retrieval", "handoff.py", "retrieve", "--directory", self.directory / "handoff")
        key = json.loads((self.directory / "handoff" / "axonhub-key.json").read_text())
        assert key["model"] == "deepseek/deepseek-v4.1-flash-1017"
        assert key["reasoning_effort"] == "high"
        binary = self.args.cli.resolve() if self.args.cli else self.directory / "multica"
        if not self.args.cli:
            archive = self.directory / "multica-cli-0.6.1-linux-amd64.tar.gz"
            url = "https://github.com/multica-ai/multica/releases/download/v0.6.1/multica-cli-0.6.1-linux-amd64.tar.gz"
            with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
            with tarfile.open(archive, "r:gz") as source, binary.open("wb") as output:
                shutil.copyfileobj(source.extractfile("multica"), output)
            binary.chmod(0o755)
        with binary.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == CLI_SHA256
        self.binary = binary
        self.checkpoint("pinned-inputs")

    def smoke(self, phase):
        self.step("preflight-" + phase, "pi-smoke.py", "--controller-state", self.state, "--phase", phase)
        trial = Trial(self.state)
        summary = json.loads((self.directory / ("pi-smoke-" + phase) / "summary.json").read_text())
        self.operation.setdefault("preflights", {})[phase] = summary
        trial.data["preflights"] = self.operation["preflights"]
        trial.save()

    def collect(self):
        self.step("evidence-collection", "collect.py", "--state", self.state,
                  "--output", self.directory / "evidence", "--scheduler-state", self.scheduler,
                  "--meta-key", self.directory / "handoff" / "swh6-ed25519", "--since",
                  self.operation["started_at"], window=False)

    def execute(self):
        self.prepare()
        if self.args.validate_inputs_only:
            print(json.dumps({"trial": self.args.trial, "toolkit_revision": self.operation["toolkit_revision"],
                              "handoff": "retrieved", "multica_binary_sha256": CLI_SHA256,
                              "inputs": "verified"}))
            return
        try:
            self.step("infrastructure-create", "infra.py", "--state", self.state, "create", "--trial", self.args.trial,
                      "--ami", self.args.ami)
            self.step("base-install", "infra.py", "--state", self.state, "base", "--node-package-version", self.args.node_package_version)
            self.step("controller-install", "controller-bootstrap.py", "--state", self.state, "--cli", self.binary, "install")
            self.step("controller-login", "controller-bootstrap.py", "--state", self.state, "login")
            self.step("pi-provision", "pi-provision.py", "--controller-state", self.state,
                      "--axonhub-key-json", self.directory / "handoff" / "axonhub-key.json",
                      "--system-text", SYSTEM, "--subjects", self.args.subjects)
            self.smoke("normal")
            self.step("network-lockdown", "infra.py", "--state", self.state, "lockdown")
            self.step("network-verification", "infra.py", "--state", self.state, "verify")
            self.smoke("restricted")
            trial = Trial(self.state)
            self.step("subject-activations", "trial-schedule.py", "--controller-state", self.state,
                      "--runtime-id", trial.data["pi_runtime_id"], "--subjects", self.args.subjects,
                      "--state-dir", self.scheduler, "--deadline", self.args.deadline)
        finally:
            try:
                if (self.scheduler / "subjects.json").exists():
                    self.collect()
            finally:
                if self.state.exists():
                    self.step("owned-resource-teardown", "infra.py", "--state", self.state, "teardown", window=False)
        summary = json.loads((self.directory / "evidence" / "sanitized" / "summary.json").read_text())
        summary["cleanup"] = Trial(self.state).data["cleanup"]
        write(self.directory / "evidence" / "sanitized" / "summary.json", summary)
        print(json.dumps({"trial": self.args.trial, "subjects": summary["subject_count"],
                          "activations": summary["activation_count"], "infrastructure": "terminated",
                          "evidence_archive": "evidence/sanitized/evidence.tar.xz"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial", required=True)
    parser.add_argument("--subjects", required=True, type=int, choices=[2, 4, 6, 8, 10])
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--toolkit-revision", required=True)
    parser.add_argument("--cli", type=Path)
    parser.add_argument("--ami", default="ami-04de259f26cbf4c1e")
    parser.add_argument("--node-package-version", default="22.23.4-1nodesource1")
    parser.add_argument("--deadline", default="2026-10-22T06:00:00Z")
    parser.add_argument("--validate-inputs-only", action="store_true")
    os.umask(0o077)
    Operator(parser.parse_args()).execute()
