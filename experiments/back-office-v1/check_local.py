#!/usr/bin/env python3
"""Run a task's waves against a local back office without Docker and score each one.

    check_local.py TASK_DIR [--arm team|solo] [--runs oracle|idle|bypass]

oracle runs steps/<wave>/solution/solve.sh, idle runs nothing, bypass runs
checks/<task>/<wave>-bypass.sh. Prints the reward keys per wave.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARED = HERE / "shared"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run(task, arm, mode):
    truth = json.loads((task / "truth.json").read_text())
    tmp = Path(tempfile.mkdtemp())
    port = free_port()
    env = dict(os.environ, WORLD_SEED=str(task / "seed.json"), WORLD_AUDIT=str(tmp / "audit.jsonl"),
               WORLD_STATE=str(tmp / "state.json"),
               WORLD_ARM=arm, WORLD_PORT=str(port), PYTHONPATH=f"{task}:{SHARED}")
    server = subprocess.Popen([sys.executable, str(SHARED / "server.py")], env=env, cwd=task)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/health", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        bindir = tmp / "bin"
        bindir.mkdir()
        (bindir / "ops").symlink_to(SHARED / "ops")
        run_env = dict(os.environ, OPS_API=base, PATH=f"{bindir}:{os.environ['PATH']}")
        results = {}
        for step in truth["steps"]:
            script = {"oracle": task / "steps" / step / "solution" / "solve.sh",
                      "bypass": HERE / "checks" / task.name / f"{step}-bypass.sh"}.get(mode)
            if script is not None:
                if not script.exists():
                    results[step] = "no script"
                    continue
                p = subprocess.run(["bash", str(script)], env=run_env, capture_output=True, text=True)
                if p.returncode:
                    print(p.stdout[-2000:], p.stderr[-2000:], file=sys.stderr)
                    results[step] = f"script failed ({p.returncode})"
                    continue
            out = tmp / "verifier" / step
            subprocess.run([sys.executable, str(SHARED / "compute_reward.py"), "--step", step,
                            "--state", str(tmp / "state.json"), "--audit", str(tmp / "audit.jsonl"),
                            "--truth", str(task / "truth.json"), "--output-dir", str(out)],
                           check=True, capture_output=True)
            results[step] = json.loads((out / "reward.json").read_text())
        return results
    finally:
        server.terminate()
        server.wait()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("task")
    p.add_argument("--arm", default="team")
    p.add_argument("--runs", default="oracle")
    a = p.parse_args()
    for step, r in run(Path(a.task).resolve(), a.arm, a.runs).items():
        if isinstance(r, dict):
            r = " ".join(f"{k}={v:g}" for k, v in r.items())
        print(f"{a.runs:7} {a.arm:5} {step}: {r}")


if __name__ == "__main__":
    main()
