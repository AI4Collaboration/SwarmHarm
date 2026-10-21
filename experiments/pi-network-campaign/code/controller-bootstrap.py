import argparse
import json
import os
from pathlib import Path
import queue
import re
import shlex
import subprocess
import threading
import time

from playwright.sync_api import sync_playwright

from infra import Trial, TEMPLATES


def controller_command(trial, *args):
    return trial.ssh("controller", "cd /home/ubuntu && " + shlex.join(["/usr/local/bin/multica", *args]), capture=True)


def install(trial, cli):
    trial.copy("controller", cli, "/home/ubuntu/campaign-bootstrap/multica")
    trial.ssh("controller", "sudo install -m 755 /home/ubuntu/campaign-bootstrap/multica /usr/local/bin/multica")
    for name in ("controller-install.py", "controller-http.conf.j2", "controller-https.conf.j2"):
        trial.copy("controller", TEMPLATES / name, f"/home/ubuntu/campaign-bootstrap/{name}")
    address = trial.data["instances"]["controller"]["public_ip"]
    trial.ssh("controller", shlex.join(["sudo", "python3", "/home/ubuntu/campaign-bootstrap/controller-install.py",
        "--address", address, "--templates", "/home/ubuntu/campaign-bootstrap"]))


def login(trial):
    temporary = trial.path.parent / "browser-tmp"
    temporary.mkdir(exist_ok=True, mode=0o700)
    for name in ("TMPDIR", "TMP", "TEMP"):
        os.environ[name] = str(temporary)
    address = trial.data["instances"]["controller"]["public_ip"]
    url = f"https://{address}"
    for key in ("server_url", "app_url"):
        controller_command(trial, "config", "set", key, url)
    ssh = ["ssh", *trial.ssh_options(), f"ubuntu@{address}"]
    child = subprocess.Popen([*ssh, "cd /home/ubuntu && /usr/local/bin/multica login --callback-host 127.0.0.1"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    messages = queue.Queue()
    log = []

    def read_messages():
        for line in child.stdout:
            log.append(line)
            messages.put(line)

    reader = threading.Thread(target=read_messages)
    reader.start()
    tunnel = None
    try:
        deadline = time.monotonic() + 180
        login_url = None
        while time.monotonic() < deadline:
            line = messages.get(timeout=30)
            match = re.search(r"https://\S+/login\?\S+", line)
            if match:
                login_url = match.group(0)
                break
        assert login_url, "CLI login URL required"
        from urllib.parse import parse_qs, urlparse
        callback = parse_qs(urlparse(login_url).query)["cli_callback"][0]
        port = urlparse(callback).port
        tunnel = subprocess.Popen(["ssh", *trial.ssh_options(), "-N", "-L", f"127.0.0.1:{port}:127.0.0.1:{port}",
            "-o", "ExitOnForwardFailure=yes", f"ubuntu@{address}"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(login_url, wait_until="networkidle", timeout=60000)
            page.locator("#login-email").fill("admin@tac.ch")
            page.locator('button[form="login-form"]').click()
            page.locator('input[autocomplete="one-time-code"]').wait_for(timeout=30000)
            logs = trial.ssh("controller", "sudo docker compose --project-directory /opt/multica logs backend --since 2m", capture=True)
            matches = re.findall(r"Verification code for admin@tac.ch: (\d{6})", logs.stdout)
            assert matches, "Server verification code required"
            page.locator('input[autocomplete="one-time-code"]').fill(matches[-1])
            page.wait_for_url(re.compile(r"http://127\.0\.0\.1:\d+/callback.*"), timeout=60000)
            while time.monotonic() < deadline:
                line = messages.get(timeout=30)
                if "Token saved to config" in line:
                    break
            else:
                raise TimeoutError("CLI saved-token confirmation required")
            workspace = json.loads(controller_command(trial, "workspace", "create", "--name", "Workspace", "--slug", "workspace",
                "--issue-prefix", "TASK", "--output", "json").stdout)
            browser.close()
        child.wait(timeout=30)
        assert child.returncode == 0, "CLI authentication completion required"
        reader.join(timeout=5)
        config = json.loads(trial.ssh("controller", "cat /home/ubuntu/.multica/config.json", capture=True).stdout)
        workspace_id = workspace["id"]
        controller_command(trial, "config", "set", "workspace_id", workspace_id)
        account = {"server_url": url, "pat": config["token"], "workspace_id": workspace_id}
        path = trial.path.parent / "account.json"
        path.touch(mode=0o600)
        path.write_text(json.dumps(account, indent=2) + "\n")
        trial.data["account_file"] = str(path)
        trial.save()
        print(json.dumps({"server_url": url, "workspace_id": workspace_id, "authentication": "CLI login"}))
    finally:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        if tunnel and tunnel.poll() is None:
            tunnel.terminate()
            tunnel.wait(timeout=10)
        reader.join(timeout=5)
        (trial.path.parent / "controller-login.log").write_text("".join(log))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--cli", type=Path)
    parser.add_argument("action", choices=("install", "login"))
    args = parser.parse_args()
    trial = Trial(args.state)
    if args.action == "install":
        assert args.cli
        install(trial, args.cli)
    else:
        login(trial)
