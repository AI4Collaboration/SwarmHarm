"""Four real workstations against a local scripted Chat Completions server."""

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import gzip
import hashlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from swarmform.__main__ import collect, source_digest


class APICollectChecks(unittest.TestCase):
    def test_four_workstations_capture_tools_and_stop(self):
        observed = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                observed.append((self.path, request))
                continued = any(m["role"] == "tool" for m in request["messages"])
                message = (
                    {"role": "assistant", "content": "Fixture completed."}
                    if continued
                    else {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_fixture",
                                "type": "function",
                                "function": {
                                    "name": "bash",
                                    "arguments": json.dumps(
                                        {
                                            "command": "cat /workspace/task.md; mkdir -p /workspace/output; printf 'captured' > /workspace/output/fixture.txt"
                                        }
                                    ),
                                },
                            }
                        ],
                    }
                )
                result = {
                    "id": "fixture",
                    "object": "chat.completion",
                    "model": request["model"],
                    "choices": [
                        {
                            "index": 0,
                            "message": message,
                            "finish_reason": "stop" if continued else "tool_calls",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 10,
                        "total_tokens": 20,
                    },
                }
                data = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as directory:
                out = Path(directory) / "cohort"
                args = SimpleNamespace(
                    population=4,
                    names="numbered",
                    task="planning-possible",
                    channel="filesystem",
                    seconds=60,
                    model="scripted-software-fixture",
                    served_model="served-fixture-alias",
                    revision="fixture",
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    key_file=None,
                    out=out,
                )
                self.assertEqual(asyncio.run(collect(args)), 0)
                summary = json.loads((out / "summary.json").read_text())
                self.assertEqual(
                    source_digest(out / "code"),
                    json.loads((out / "registration.json").read_text())[
                        "source_sha256"
                    ],
                )
                self.assertEqual(len(summary["finished"]), 4)
                self.assertTrue(summary["physical_stop_verified"])
                self.assertEqual(len(observed), 8)
                self.assertEqual(
                    {request["model"] for _, request in observed},
                    {"served-fixture-alias"},
                )
                self.assertTrue(
                    all(path == "/v1/chat/completions" for path, _ in observed)
                )
                for actor in summary["finished"]:
                    with gzip.open(out / (actor + ".jsonl.gz"), "rt") as stream:
                        events = [json.loads(line) for line in stream]
                    self.assertEqual(sum(e["kind"] == "tool_result" for e in events), 1)
                    self.assertEqual(sum(e["kind"] == "response" for e in events), 2)
                manifest = json.loads((out / "evidence-manifest.json").read_text())
                for name, expected in manifest.items():
                    self.assertEqual(
                        hashlib.sha256((out / name).read_bytes()).hexdigest(), expected
                    )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_cli_interrupt_seals_active_tools_and_stops_the_batch(self):
        root = Path(__file__).resolve().parents[2]

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                body = json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "slow_tool",
                                            "type": "function",
                                            "function": {
                                                "name": "bash",
                                                "arguments": json.dumps(
                                                    {
                                                        "command": "printf started; sleep 25"
                                                    }
                                                ),
                                            },
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                        "usage": {"total_tokens": 20},
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as directory:
                out = Path(directory) / "batch"
                command = [
                    sys.executable,
                    str(root / "rollouts/run_matrix.py"),
                    "--model",
                    "fixture",
                    "--harness",
                    "chat-completions",
                    "--populations",
                    "2",
                    "--tasks",
                    "planning-possible",
                    "--base-url",
                    f"http://127.0.0.1:{server.server_port}/v1",
                    "--execute",
                    "--out",
                    str(out),
                ]
                with (Path(directory) / "batch.log").open("w+") as log:
                    process = subprocess.Popen(
                        command, cwd=root, stdout=log, stderr=log
                    )
                    try:
                        deadline = time.monotonic() + 45
                        active = False
                        while time.monotonic() < deadline and process.poll() is None:
                            for path in out.glob("**/Research*.jsonl.gz"):
                                try:
                                    with gzip.open(path, "rt") as stream:
                                        active = active or any(
                                            json.loads(line)["kind"] == "tool_start"
                                            for line in stream
                                        )
                                except (EOFError, OSError):
                                    continue
                            if active:
                                break
                            time.sleep(0.05)
                        self.assertTrue(
                            active, "Collector never reached an active tool"
                        )
                        process.send_signal(signal.SIGTERM)
                        self.assertEqual(process.wait(timeout=60), 1)
                    finally:
                        if process.poll() is None:
                            process.send_signal(signal.SIGTERM)
                            process.wait(timeout=60)
                index = json.loads((out / "index.json").read_text())
                self.assertEqual(len(index["runs"]), 1)
                run = Path(index["runs"][0]["output"])
                summary = json.loads((run / "summary.json").read_text())
                self.assertFalse(summary["complete"])
                self.assertEqual(summary["reason"], "operator_interrupt")
                self.assertTrue(summary["physical_stop_verified"])
                manifest = json.loads((run / "evidence-manifest.json").read_text())
                for name, expected in manifest.items():
                    self.assertEqual(
                        hashlib.sha256((run / name).read_bytes()).hexdigest(), expected
                    )
                events = []
                for path in run.glob("Research*.jsonl.gz"):
                    with gzip.open(path, "rt") as stream:
                        events.extend(json.loads(line) for line in stream)
                started = {e["call_id"] for e in events if e["kind"] == "tool_start"}
                completed = {
                    e["call_id"]
                    for e in events
                    if e["kind"] in ("tool_result", "tool_error")
                }
                self.assertTrue(started <= completed)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_distributed_sources_remain_private_in_common_workspace(self):
        from swarmform import formation_inputs as inputs
        from swarmform.formation_common import CommonWorkspace

        for family in ("decoder", "planning"):
            with self.subTest(family=family), TemporaryDirectory() as directory:
                visible, _, _ = inputs.build_intended(
                    family + "-distributed", 3, names="numbered"
                )
                station = CommonWorkspace(
                    visible["startup"],
                    {"population": 3},
                    observation_archive=Path(directory) / "reads",
                )
                try:
                    for binding in station.bindings.values():
                        self.assertTrue(binding["initial_materials_verified"])
                        self.assertEqual(len(binding["access_control"]["denied"]), 2)
                        self.assertTrue(
                            all(
                                "/calibrations/" in path or "/calendars/" in path
                                for path in binding["access_control"]["denied"]
                            )
                        )
                finally:
                    station.close()

    def test_socket_and_memory_preserve_foreign_writes_and_private_sources(self):
        from swarmform import formation_inputs as inputs
        from swarmform.formation_deployment import deployment

        for channel in ("socket", "mapped_memory"):
            with self.subTest(channel=channel), TemporaryDirectory() as directory:
                visible, _, _ = inputs.build(
                    "planning-distributed", channel, 2, names="numbered"
                )
                instance = deployment(
                    visible["startup"],
                    {"channel_family": channel, "deployment": {"shared": True}},
                    observation_archive=Path(directory) / "reads",
                )
                try:
                    first, second = instance.stations
                    private = next(
                        p
                        for p in visible["startup"][first]
                        if "/calendars/" in p and p not in visible["startup"][second]
                    )
                    result, _ = instance.execute(second, "test ! -e " + private)
                    self.assertEqual(result["exit_code"], 0)
                    result, _ = instance.execute(
                        first,
                        "printf 'fixture payload' > /workspace/payload.txt; "
                        "python /workspace/projects.py write probe /workspace/payload.txt",
                    )
                    self.assertEqual(result["exit_code"], 0, result)
                    result, _ = instance.execute(
                        second, "python /workspace/projects.py read probe"
                    )
                    self.assertEqual(result["exit_code"], 0, result)
                    self.assertEqual(
                        json.loads(result["stdout"])["text"], "fixture payload"
                    )
                finally:
                    instance.close()
                self.assertTrue(instance.closed)
                self.assertIsNotNone(instance.terminal_service)

    def test_decoder_grading_uses_protected_answers_and_determinism(self):
        from swarmform import formation_engineering as decoder
        from swarmform.artifact_runner import execute_release

        _, complete, _ = decoder.build("decoder-possible", 3)
        _, impossible, _ = decoder.build("decoder-impossible", 3)
        source = decoder.wire.compile_reference(
            complete["records"], decoder.wire.CUTOFFS[0]
        )
        self.assertTrue(
            execute_release(source, complete["probes"]["candidate"])["complete"]
        )
        partial = execute_release(source, impossible["probes"]["candidate"])
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["correct_probes"], 4)
        answers = [answer for _, answer in impossible["probes"]["candidate"]]
        alternating = (
            "import json\nrows=json.loads("
            + repr(json.dumps(answers))
            + ")\ndef decode(frame):\n return rows.pop(0)\n"
        )
        forged = execute_release(alternating, impossible["probes"]["candidate"])
        self.assertEqual(forged["correct_probes"], 8)
        self.assertFalse(forged["complete"])
        self.assertFalse(forged["deterministic_on_repeated_frames"])


if __name__ == "__main__":
    unittest.main()
