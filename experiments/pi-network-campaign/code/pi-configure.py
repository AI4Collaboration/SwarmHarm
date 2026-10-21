import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess


SYSTEM_SHA256 = "44a5fc31a371e626ccaaf3c77f737ac123338319163f34f992abee407751e525"
MODEL = "deepseek/deepseek-v4.1-flash-1017"
PROVIDER = "axonhub-campaign"


def write_owned(path, data, account, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)
    path.chmod(mode)
    os.chown(path, account.pw_uid, account.pw_gid)


def configure(args):
    account = pwd.getpwnam(args.user)
    agent_home = Path(account.pw_dir)
    system = args.system_text.read_bytes()
    assert len(system) == 3010, "System attachment size must equal 3010 bytes"
    assert hashlib.sha256(system).hexdigest() == SYSTEM_SHA256, "System attachment digest must match the campaign registration"
    key = args.axonhub_key_file.read_text(encoding="utf-8").strip()
    assert key, "AxonHub key must contain a value"
    pi_dir = agent_home / ".pi" / "agent"
    pi_dir.mkdir(parents=True, exist_ok=True)
    for directory in (agent_home / ".pi", pi_dir):
        directory.chmod(0o700)
        os.chown(directory, account.pw_uid, account.pw_gid)
    model_config = {
        "providers": {
            PROVIDER: {
                "baseUrl": args.axonhub_url.rstrip("/") + "/v1",
                "api": "openai-completions",
                "apiKey": key,
                "headers": {
                    "X-SWH119-Trial": args.trial_id,
                    "X-SWH119-Subject": "MULTICA_AGENT_ID",
                },
                "models": [{
                    "id": MODEL,
                    "reasoning": True,
                    "input": ["text"],
                    "thinkingLevelMap": {"high": "high"},
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsStore": False,
                        "thinkingFormat": "openrouter",
                        "requiresReasoningContentOnAssistantMessages": True,
                    },
                }],
            }
        }
    }
    settings = {
        "defaultProvider": PROVIDER,
        "defaultModel": MODEL,
        "defaultThinkingLevel": "high",
    }
    write_owned(pi_dir / "models.json", json.dumps(model_config, indent=2) + "\n", account)
    write_owned(pi_dir / "settings.json", json.dumps(settings, indent=2) + "\n", account)
    write_owned(pi_dir / "SYSTEM.md", system, account)
    if args.configure_daemon:
        assert args.operator_token_file and args.server_url and args.workspace_id and args.proxy_ip and args.device_name
        assert args.server_url.startswith("https://"), "Controller transport must use HTTPS"
        token = args.operator_token_file.read_text(encoding="utf-8").strip()
        proxy = "http://" + args.proxy_ip + ":3128"
        user_environment = os.environ | {
            "HTTP_PROXY": proxy,
            "HTTPS_PROXY": proxy,
            "http_proxy": proxy,
            "https_proxy": proxy,
            "NO_PROXY": "localhost,127.0.0.1,::1,169.254.169.123",
            "no_proxy": "localhost,127.0.0.1,::1,169.254.169.123",
        }
        base = ["sudo", "-u", args.user, "-H", "env"]
        base.extend(f"{name}={value}" for name, value in user_environment.items() if name in {
            "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "NO_PROXY", "no_proxy"
        })
        for command in (
            ["config", "set", "server_url", args.server_url],
            ["config", "set", "app_url", args.server_url],
            ["login", "--token", token],
            ["config", "set", "workspace_id", args.workspace_id],
        ):
            result = subprocess.run(base + [args.multica] + command, capture_output=True, text=True)
            assert result.returncode == 0, "Lab CLI configuration must complete: " + result.stderr.replace(token, "[credential]")
        unit = "\n".join([
            "[Unit]",
            "Description=Multica campaign Pi runtime",
            "Wants=network-online.target",
            "After=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"User={args.user}",
            f"WorkingDirectory={agent_home}",
            "Environment=PATH=/usr/local/bin:/usr/bin:/bin",
            f"Environment=HOME={agent_home}",
            f"Environment=HTTP_PROXY={proxy}",
            f"Environment=HTTPS_PROXY={proxy}",
            f"Environment=http_proxy={proxy}",
            f"Environment=https_proxy={proxy}",
            "Environment=NO_PROXY=localhost,127.0.0.1,::1,169.254.169.123",
            "Environment=no_proxy=localhost,127.0.0.1,::1,169.254.169.123",
            "Environment=MULTICA_DAEMON_AUTO_UPDATE=false",
            "Environment=MULTICA_DAEMON_AUTO_RELOAD=false",
            f"ExecStart={args.multica} daemon start --foreground --device-name {args.device_name} --max-concurrent-tasks {args.concurrency} --agent-timeout {args.agent_timeout} --no-auto-update --no-auto-reload",
            "Restart=on-failure",
            "RestartSec=5",
            "UMask=0077",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ])
        unit_path = Path("/etc/systemd/system/multica-runtime.service")
        unit_path.write_text(unit, encoding="utf-8")
        unit_path.chmod(0o600)
        cutoff = datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
        assert cutoff.tzinfo and datetime.now(timezone.utc) < cutoff, "Runtime cutoff must be a future time with an explicit UTC offset"
        cutoff = cutoff.astimezone(timezone.utc)
        stop_service = Path("/etc/systemd/system/multica-runtime-cutoff.service")
        stop_service.write_text("\n".join([
            "[Unit]",
            "Description=Stop campaign subjects at the approved deadline",
            "",
            "[Service]",
            "Type=oneshot",
            "ExecStart=/usr/bin/systemctl stop multica-runtime.service",
            "",
        ]), encoding="utf-8")
        stop_service.chmod(0o644)
        stop_timer = Path("/etc/systemd/system/multica-runtime-cutoff.timer")
        stop_timer.write_text("\n".join([
            "[Unit]",
            "Description=Campaign subject deadline",
            "",
            "[Timer]",
            "OnCalendar=" + cutoff.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "AccuracySec=1s",
            "Persistent=true",
            "Unit=multica-runtime-cutoff.service",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]), encoding="utf-8")
        stop_timer.chmod(0o644)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "--now", "multica-runtime-cutoff.timer"], check=True)
        subprocess.run(["systemctl", "enable", "--now", "multica-runtime.service"], check=True)
        subprocess.run(["systemctl", "is-active", "multica-runtime.service"], check=True)
    print(json.dumps({
        "pi_version": "0.73.1",
        "multica_version": "0.6.1",
        "model": MODEL,
        "model_selector": PROVIDER + "/" + MODEL,
        "reasoning": {"effort": "high"},
        "system_sha256": SYSTEM_SHA256,
        "custom_args": ["--system-prompt", str(pi_dir / "SYSTEM.md")],
    }, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="agent")
    parser.add_argument("--axonhub-key-file", type=Path, required=True)
    parser.add_argument("--axonhub-url", default="https://lmportal.iefbr14.xyz")
    parser.add_argument("--system-text", type=Path, required=True)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--configure-daemon", action="store_true")
    parser.add_argument("--operator-token-file", type=Path)
    parser.add_argument("--server-url")
    parser.add_argument("--workspace-id")
    parser.add_argument("--proxy-ip")
    parser.add_argument("--device-name")
    parser.add_argument("--concurrency", type=int, choices=range(1, 11), default=1)
    parser.add_argument("--agent-timeout", default="15m")
    parser.add_argument("--deadline", default="2026-10-22T06:00:00Z")
    parser.add_argument("--multica", default="/usr/local/bin/multica")
    configure(parser.parse_args())


if __name__ == "__main__":
    main()
