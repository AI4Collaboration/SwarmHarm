"""Run the four published processing cases against a reference or an isolated replacement."""
import argparse
import hashlib
import json
import os
import shlex
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET


ARCHIVE_SHA256 = "a35ec641cd71b298ea6abe24f7f0947fc3f461ef44caa88672b0dbf4f911dac7"
SOURCE = ("https://huggingface.co/datasets/programbench/ProgramBench-Tests/resolve/"
          "5954a1957b5e0d770ec2c5523506abd212806315/ffmpeg__ffmpeg.360a402/tests/924e9dacd43b.tar.gz")


def relay(container, exe, scratch, argv):
    call = ["docker", "exec", "-i", container]
    paths, args = [], []
    for arg in argv:
        path = Path(arg)
        if not path.is_absolute() or not path.is_relative_to(scratch):
            args.append(arg)
            continue
        dest = Path("/tmp") / path.relative_to(scratch)
        args.append(str(dest))
        paths.append((path, dest))
        subprocess.run([*call, "mkdir", "-p", str(dest.parent)], check=True)
        if path.is_file():
            with path.open("rb") as stream:
                subprocess.run([*call, "sh", "-c", 'cat > "$1"', "sh", str(dest)], stdin=stream, check=True)
    result = subprocess.run([*call, exe, *args], timeout=8)
    for path, dest in paths:
        reply = subprocess.run([*call, "cat", str(dest)], capture_output=True)
        if reply.returncode == 0:
            path.write_bytes(reply.stdout)
    return result.returncode


def score(archive, image, candidate=None, candidate_root=None):
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != ARCHIVE_SHA256:
            raise ValueError("Unexpected upstream archive digest")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        tests = root / "eval/tests"
        tests.mkdir(parents=True)
        with tarfile.open(archive) as upstream:
            for name in ("conftest.py", "test_processing.py"):
                (tests / name).write_bytes(upstream.extractfile("eval/tests/" + name).read())
        scratch = root / "scratch"
        scratch.mkdir()
        scratch.chmod(0o777)
        args = ["docker", "run", "-d", "--rm", "--pull=never", "--network=none",
                "--user", "65534:65534", "--read-only", "--cap-drop=ALL", "--memory=256m",
                "--pids-limit=64", "--tmpfs", "/tmp:rw,size=32m,mode=1777"]
        exe = "/opt/reference/ffmpeg"
        if candidate is not None:
            candidate = candidate.absolute()
            project = candidate_root.resolve(strict=True) if candidate_root else candidate.parent.resolve(strict=True)
            relative = (candidate.parent.resolve(strict=True) / candidate.name).relative_to(project)
            if not candidate.resolve(strict=True).is_relative_to(project):
                raise ValueError("Submitted executable resolves outside its project")
            args += ["--tmpfs", "/candidate:rw,exec,size=64m,mode=755,uid=65534,gid=65534",
                     "--tmpfs", "/opt/reference:ro,size=1m"]
            exe = "/candidate/" + relative.as_posix()
        container = subprocess.check_output([*args, image, "sleep", "300"], text=True).strip()
        try:
            if candidate:
                # Stream through the container process to support remote Docker daemons.
                with subprocess.Popen(["tar", "--no-xattrs", "-C", str(project), "-cf", "-", "."],
                                      stdout=subprocess.PIPE, env={**os.environ, "COPYFILE_DISABLE": "1"}) as packed:
                    subprocess.run(["docker", "exec", "-i", container, "tar",
                                    "--no-same-owner", "-xf", "-", "-C", "/candidate"],
                                   stdin=packed.stdout, check=True)
                    if packed.wait():
                        raise RuntimeError("Could not read candidate")
                subprocess.run(["docker", "exec", container, "test", "-x", exe], check=True)
            wrapper = root / "executable"
            # Unlike copying an entire host tree, copying the path arguments leaves
            # pytest's own basetemp permissions, symlinks and ownership untouched.
            relay_command = shlex.join([sys.executable, str(Path(__file__).resolve()), "--relay",
                                        container, exe, str(scratch)])
            wrapper.write_text(f'#!/bin/sh\nexec {relay_command} "$@"\n')
            wrapper.chmod(0o755)
            report = root / "results.xml"
            run = subprocess.run([sys.executable, "-m", "pytest", "-q", str(tests),
                                  "--basetemp", str(scratch / "tests"), "--junitxml", str(report)],
                                 cwd=root, capture_output=True, text=True, timeout=120)
            if run.returncode not in (0, 1) or not report.is_file():
                raise RuntimeError(run.stdout[-1500:] + run.stderr[-1500:])
            cases = {c.get("name"): not any(c.find(t) is not None for t in ("failure", "error", "skipped"))
                     for c in ET.parse(report).iter("testcase")}
            if candidate is None and not all(cases.values()):
                raise RuntimeError("Reference failed upstream controls: " + run.stdout[-6000:])
            if len(cases) != 4:
                raise RuntimeError("Upstream processing case count changed")
            return {"suite": "924e9dacd43b/test_processing.py", "archive_sha256": ARCHIVE_SHA256,
                    "cases": cases, "passed": sum(cases.values()), "total": len(cases)}
        finally:
            subprocess.run(["docker", "rm", "-f", container], check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--relay"]:
        raise SystemExit(relay(sys.argv[2], sys.argv[3], Path(sys.argv[4]), sys.argv[5:]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-archive", required=True, type=Path, help=SOURCE)
    parser.add_argument("--image", required=True, help="Frozen SwarmForm media image")
    parser.add_argument("--candidate", type=Path, help="Executable with its dependencies in the same directory")
    parser.add_argument("--candidate-root", type=Path, help="Project directory containing the executable and its relative dependencies")
    args = parser.parse_args()
    if args.candidate_root and not args.candidate:
        parser.error("--candidate-root requires --candidate")
    print(json.dumps(score(args.test_archive, args.image, args.candidate, args.candidate_root), indent=2))
