"""Focused offline regressions for the portable SwarmForm collector."""

import asyncio
from contextlib import contextmanager
import errno
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import secrets
import subprocess
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from argparse import Namespace

import httpx
from swarmform import formation_inputs as inputs
from swarmform.__main__ import Cohort
from swarmform.file_deployment import FileDeployment
from swarmform.formation_common import CommonWorkspace
from swarmform.read_observer import ObservedFileStation, trace_blocks


@contextmanager
def endpoint():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert self.path == "/v1/chat/completions"
            if body["messages"][-1]["role"] == "tool":
                message = {"role": "assistant", "content": "Done."}
                finish = "stop"
            else:
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps(
                                    {"command": "cat /workspace/task.md | head -c 160"}
                                ),
                            },
                        }
                    ],
                }
                finish = "tool_calls"
            data = json.dumps(
                {
                    "id": "fixture",
                    "choices": [{"message": message, "finish_reason": finish}],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 4,
                        "total_tokens": 24,
                    },
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.station = ObservedFileStation.__new__(ObservedFileStation)
        self.station.configure_archive(Path(self.folder.name) / "reads")
        (self.station.archive / "chunks").mkdir()
        self.station.name = "test-station"

    def capture(self, content, offset=0, closed=False):
        header = {
            "files": [
                {
                    "name": "000001.log",
                    "bytes": offset + len(content),
                    "offset": offset,
                    "device": 1,
                    "inode": 2,
                    "complete_line": True,
                }
            ],
            "closed": ["000001.log"] if closed else [],
            "guest_clock": {"boot_id": "test"},
        }
        stream = io.BytesIO(json.dumps(header).encode() + b"\n" + content)
        now = time.monotonic_ns()
        parsed = self.station.archive_capture(stream, now)
        return self.station.commit_capture(*parsed, now)

    def test_append_hashes_and_retains_old_versions(self):
        first = b"hello\n" * 300000
        receipt = self.capture(first)
        old = json.loads(Path(receipt["path"]).read_bytes())["files"]["000001.log"]
        suffix = b"world\n" * 20000
        self.capture(suffix, len(first))
        current = self.station.trace_files["000001.log"]
        self.assertEqual(b"".join(trace_blocks(self.station.archive, old)), first)
        self.assertEqual(
            b"".join(trace_blocks(self.station.archive, current)), first + suffix
        )
        self.assertEqual(old["chunks"], current["chunks"][: len(old["chunks"])])
        record = json.loads((self.station.archive / "000002.json").read_bytes())
        self.assertEqual(record["storage"]["transferred_bytes"], len(suffix))

    def test_write_failure_preserves_last_committed_receipt_and_no_pruning(self):
        self.capture(b"first\n")
        with (
            patch(
                "swarmform.read_observer.atomic_json",
                side_effect=OSError(errno.ENOSPC, "full"),
            ),
            patch("swarmform.read_observer.subprocess.run") as prune,
        ):
            with self.assertRaises(OSError):
                self.capture(b"second\n", 6, closed=True)
            prune.assert_not_called()
        self.assertEqual(self.station.previous["000001.log"], b"first\n")
        with patch("swarmform.read_observer.subprocess.run"):
            self.capture(b"second\n", 6, closed=True)
        self.assertEqual(self.station.previous["000001.log"], b"first\nsecond\n")

    def test_corruption_is_reported(self):
        self.capture(b"verified\n")
        record = self.station.trace_files["000001.log"]
        (self.station.archive / record["chunks"][0]["blob"]).write_bytes(
            gzip.compress(b"bad")
        )
        with self.assertRaises(RuntimeError):
            list(trace_blocks(self.station.archive, record))

    def test_old_uncompressed_archive(self):
        raw = b"old trace\n"
        (self.station.archive / "old").write_bytes(raw)
        record = {
            "blob": "old",
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        self.assertEqual(b"".join(trace_blocks(self.station.archive, record)), raw)


class LifecycleTests(unittest.TestCase):
    def test_one_failed_capture_keeps_all_resources_and_attempts_all_agents(self):
        for cls in (FileDeployment, CommonWorkspace):
            with self.subTest(cls=cls):
                deployment = cls.__new__(cls)
                deployment.closed = False
                first, second = Mock(), Mock()
                first.capture_terminal.side_effect = OSError("disk full")
                deployment.stations = {"a": first, "b": second}
                deployment.resources = Mock()
                with self.assertRaises(ExceptionGroup):
                    deployment.close()
                second.capture_terminal.assert_called_once()
                deployment.resources.close.assert_not_called()
                first.capture_terminal.side_effect = None
                deployment.close()
                deployment.resources.close.assert_called_once()

    def test_cancelled_request_retains_completed_tool_result(self):
        async def check(folder):
            args = Namespace(
                task="service-plan",
                channel="direct",
                population=4,
                names="numbered",
                base_url="http://fixture/v1",
                model="fixture",
            )
            request = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "bash",
                                        "arguments": '{"command":"echo retained"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"total_tokens": 24},
            }
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda req: httpx.Response(200, json=request)
                )
            ) as client:
                cohort = Cohort(args, client, Path(folder))
                cohort.start = time.monotonic()
                started = threading.Event()

                def execute(*args):
                    started.set()
                    time.sleep(0.1)
                    return {"stdout": "retained", "exit_code": 0}, {}

                cohort.station = Mock(execute=execute)
                actor = next(iter(cohort.visible["startup"]))
                worker = asyncio.create_task(cohort.participant(actor))
                await asyncio.to_thread(started.wait, 5)
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
                await asyncio.gather(*cohort.active_tools)
                records = [
                    json.loads(line)
                    for line in gzip.open(Path(folder) / (actor + ".jsonl.gz"), "rt")
                ]
                self.assertEqual(
                    [
                        r["result"]["stdout"]
                        for r in records
                        if r["kind"] == "tool_result"
                    ],
                    ["retained"],
                )

        with tempfile.TemporaryDirectory() as folder:
            asyncio.run(check(folder))

    def test_all_requested_populations_have_matched_inputs(self):
        for population in (4, 8, 16, 32):
            for task in inputs.TASK_MODULES:
                with self.subTest(population=population, task=task):
                    cases = [inputs.build_intended(task, population, names="numbered")]
                    cases += [
                        inputs.build(task, channel, population, names="numbered")
                        for channel in inputs.CHANNELS
                    ]
                    self.assertEqual(
                        len({m["task_only_sha256"] for _, _, m in cases}), 1
                    )
                    self.assertTrue(
                        all(
                            len(v["startup"]) == population
                            and m["instruction_audit"]["passed"]
                            for v, _, m in cases
                        )
                    )


@unittest.skipUnless(
    os.environ.get("SWARMFORM_DOCKER_TESTS"), "explicit Docker storage stress test"
)
class LargeArchiveTests(unittest.TestCase):
    def test_over_two_gibibytes_losslessly_archived_and_incremental(self):
        from workstation import IMAGE

        name = "swarmform-archive-test-" + secrets.token_hex(6)
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                name,
                "--network=none",
                IMAGE,
                "sleep",
                "infinity",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.addCleanup(
            lambda: subprocess.run(
                ["docker", "rm", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
        with tempfile.TemporaryDirectory() as folder:
            station = ObservedFileStation.__new__(ObservedFileStation)
            station.configure_archive(Path(folder) / "archive")
            station.name = name
            # Both descriptors stay open while the observer crosses the previous
            # 1 GiB per-trace and 2 GiB aggregate limits.
            code = r"""
import os,time
from pathlib import Path
root=Path('/var/log/workstation');root.mkdir()
files=[(root/(str(i)+'.log')).open('wb',buffering=0) for i in range(2)]
block=b'x'*(1024*1024-1)+b'\n'
for f in files:
    for i in range(1025):f.write(block)
Path('/tmp/ready').write_text(str(os.getpid()))
while not Path('/tmp/close').exists():time.sleep(.05)
for f in files:f.close()
Path('/tmp/closed').touch()
"""
            subprocess.run(
                ["docker", "exec", "-d", name, "python", "-c", code], check=True
            )
            for _ in range(600):
                if (
                    subprocess.run(
                        ["docker", "exec", name, "test", "-f", "/tmp/ready"]
                    ).returncode
                    == 0
                ):
                    break
                time.sleep(0.1)
            else:
                self.fail("large trace creation did not finish")
            first = station.retain_traces()
            record = json.loads(Path(first["path"]).read_bytes())
            self.assertEqual(record["storage"]["captured_bytes"], 2 * 1025 * 1024**2)
            expected = hashlib.sha256()
            block = b"x" * (1024 * 1024 - 1) + b"\n"
            for _ in range(1025):
                expected.update(block)
            for trace in station.trace_files.values():
                self.assertEqual(trace["sha256"], expected.hexdigest())
                self.assertEqual(
                    sum(map(len, trace_blocks(station.archive, trace))), trace["bytes"]
                )
            subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "python",
                    "-c",
                    "open('/var/log/workstation/0.log','ab').write(b'tail\\n')",
                ],
                check=True,
            )
            with patch(
                "swarmform.read_observer.atomic_json",
                side_effect=OSError(errno.ENOSPC, "full"),
            ):
                with self.assertRaises(OSError):
                    station.retain_traces()
            second = station.retain_traces()
            record = json.loads(Path(second["path"]).read_bytes())
            self.assertEqual(record["storage"]["transferred_bytes"], 5)
            expected.update(b"tail\n")
            self.assertEqual(
                station.trace_files["0.log"]["sha256"], expected.hexdigest()
            )
            self.assertLess(
                sum(f.stat().st_size for f in (station.archive / "chunks").iterdir()),
                1024**2,
            )
            subprocess.run(["docker", "exec", name, "touch", "/tmp/close"], check=True)
            for _ in range(100):
                if (
                    subprocess.run(
                        ["docker", "exec", name, "test", "-f", "/tmp/closed"]
                    ).returncode
                    == 0
                ):
                    break
                time.sleep(0.1)
            station.retain_traces()
            self.assertEqual(set(station.pruned), {"0.log", "1.log"})
            self.assertEqual(
                subprocess.check_output(
                    ["docker", "exec", name, "ls", "-A", "/var/log/workstation"]
                ),
                b"",
            )


if __name__ == "__main__":
    unittest.main()
