import argparse
import json
from pathlib import Path
import shlex
import time

from infra import Trial, TEMPLATES


def provision(args):
    trial = Trial(args.controller_state)
    account = json.loads(Path(trial.data["account_file"]).read_text(encoding="utf-8"))
    key = json.loads(args.axonhub_key_json.read_text(encoding="utf-8"))["key"]
    private = trial.path.parent
    key_file = private / "pi-model-key"
    token_file = private / "pi-controller-token"
    for path, value in ((key_file, key), (token_file, account["pat"])):
        path.touch(mode=0o600)
        path.chmod(0o600)
        path.write_text(value, encoding="utf-8")
    root = "/home/ubuntu/campaign-bootstrap"
    trial.ssh("runtime", "mkdir -p " + root + " && chmod 700 " + root)
    for path, destination in (
        (key_file, "pi-model-key"),
        (token_file, "pi-controller-token"),
        (args.system_text, "infinite-gen-4.md"),
        (TEMPLATES / "pi-configure.py", "pi-configure.py"),
    ):
        trial.copy("runtime", path, root + "/" + destination)
    trial.ssh("runtime", "chmod 600 " + root + "/pi-model-key " + root + "/pi-controller-token")
    versions = trial.ssh("runtime", "sudo -u agent -H pi --version 2>&1 && /usr/local/bin/multica version", capture=True).stdout
    assert "0.73.1" in versions and "multica 0.6.1" in versions, "Runtime dependencies must match the campaign pins"
    command = [
        "sudo", "python3", root + "/pi-configure.py",
        "--axonhub-key-file", root + "/pi-model-key",
        "--system-text", root + "/infinite-gen-4.md",
        "--trial-id", trial.data["trial"],
        "--configure-daemon",
        "--operator-token-file", root + "/pi-controller-token",
        "--server-url", account["server_url"],
        "--workspace-id", account["workspace_id"],
        "--proxy-ip", trial.data["instances"]["proxy"]["private_ip"],
        "--device-name", trial.data["trial"] + "-runtime",
        "--concurrency", str(args.subjects),
        "--agent-timeout", args.agent_timeout,
    ]
    configured = trial.ssh("runtime", shlex.join(command), capture=True)
    (private / "pi-configuration.log").write_text(configured.stdout, encoding="utf-8")
    device_name = trial.data["trial"] + "-runtime"
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = trial.ssh("controller", "cd /home/ubuntu && /usr/local/bin/multica runtime list --output json", capture=True)
        runtimes = json.loads(result.stdout)
        candidates = [row for row in runtimes if row["provider"] == "pi" and row["status"] == "online"
                      and row["name"].endswith("(" + device_name + ")")]
        if candidates:
            assert len(candidates) == 1, "Each trial controller must register exactly one Pi runtime"
            trial.data["pi_runtime_id"] = candidates[0]["id"]
            trial.data["pi_agent_timeout"] = args.agent_timeout
            trial.save()
            print(json.dumps({"runtime_id": candidates[0]["id"], "provider": "pi", "versions": versions.strip()}))
            return
        time.sleep(3)
    raise TimeoutError("Pi runtime registration must complete within sixty seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller-state", type=Path, required=True)
    parser.add_argument("--axonhub-key-json", type=Path, required=True)
    parser.add_argument("--system-text", type=Path, required=True)
    parser.add_argument("--subjects", type=int, choices=[2, 4, 6, 8, 10], required=True)
    parser.add_argument("--agent-timeout", default="15m")
    provision(parser.parse_args())
