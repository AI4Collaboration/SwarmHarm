import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import subprocess

from infra import Trial, TEMPLATES


def smoke(args):
    trial = Trial(args.controller_state)
    output = trial.path.parent / ("pi-smoke-" + args.phase)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    uid = trial.ssh("runtime", "id -u agent", capture=True).stdout.strip()
    assert uid == "1001", "Normal subject account must use UID 1001"
    script_path = "/home/ubuntu/campaign-bootstrap/pi-smoke.sh"
    trial.copy("runtime", TEMPLATES / "pi-smoke.sh", script_path)
    command = ["sudo", "bash", script_path, args.phase, trial.data["instances"]["proxy"]["private_ip"]]
    result = subprocess.run(
        ["ssh", *trial.ssh_options(), "ubuntu@" + trial.data["instances"]["runtime"]["public_ip"], shlex.join(command)],
        capture_output=True, text=True,
    )
    stream = output / "events.jsonl"
    stream.touch(mode=0o600)
    stream.write_text(result.stdout, encoding="utf-8")
    stderr = output / "stderr.log"
    stderr.touch(mode=0o600)
    stderr.write_text(result.stderr, encoding="utf-8")
    assert result.returncode == 0, "Stock Pi smoke must complete; inspect the private captured stream and stderr"
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    starts = [row for row in events if row.get("type") == "tool_execution_start" and row.get("toolName") == "bash"]
    assert starts, "Stock Pi must execute its actual bash tool"
    call_ids = {row["toolCallId"] for row in starts}
    results = [row for row in events if row.get("type") == "tool_execution_end" and row.get("toolCallId") in call_ids]
    assert results, "Pi must capture its real shell result"
    shell_results = json.dumps(results)
    assert "uid=1001(agent)" in shell_results, "Shell output must identify the actual normal subject account"
    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", shell_results), "Shell output must contain a UTC timestamp"
    assert "/home/agent/campaign-checks/" + args.phase in shell_results, "Shell output must identify the smoke working directory"
    remote_session = "/home/agent/campaign-checks/" + args.phase + ".jsonl"
    session = trial.ssh("runtime", "sudo cat " + shlex.quote(remote_session), capture=True).stdout
    session_file = output / "session.jsonl"
    session_file.touch(mode=0o600)
    session_file.write_text(session, encoding="utf-8")
    summary = {
        "phase": args.phase,
        "at": datetime.now(timezone.utc).isoformat(),
        "uid": int(uid),
        "bash_calls": len(starts),
        "tool_results": len(results),
        "session_bytes": len(session.encode("utf-8")),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    trial.ssh("runtime", "sudo rm -rf -- /home/agent/campaign-checks")
    trial.ssh("runtime", "sudo test ! -e /home/agent/campaign-checks")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller-state", type=Path, required=True)
    parser.add_argument("--phase", choices=["normal", "restricted"], required=True)
    smoke(parser.parse_args())
