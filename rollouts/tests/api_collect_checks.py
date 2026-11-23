"""Four real workstations against a local scripted Chat Completions server."""

import asyncio
import base64
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
from unittest.mock import patch

from swarmform import checkpoint
from swarmform.__main__ import collect, source_digest


class APICollectChecks(unittest.TestCase):
    def test_four_workstations_capture_tools_and_stop(self):
        observed = []
        throttled = []
        rate_lock = threading.Lock()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                request = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                observed.append((self.path, request))
                history = request["messages"]
                reviewer = history[0]["role"] == "system"
                continued = history[-1]["role"] == "tool" or reviewer
                first_tool = not any(m["role"] == "tool" for m in history)
                if history[-1]["role"] == "tool" and not reviewer:
                    with rate_lock:
                        if not throttled:
                            throttled.append(request)
                            self.send_response(429)
                            self.send_header("Retry-After", "0")
                            self.end_headers()
                            return
                message = (
                    {"role": "assistant", "content": '{"pattern":null}' if reviewer else "Fixture completed."}
                    if continued
                    else {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": f"call_fixture_{len(history)}",
                                "type": "function",
                                "function": {
                                    "name": "bash",
                                    "arguments": json.dumps(
                                        {
                                            "command": ("sleep 5; cat /workspace/task.md; mkdir -p /workspace/output; printf 'captured' > /workspace/output/fixture.txt"
                                                        if first_tool else "sleep 0.3; cat /workspace/output/fixture.txt")
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
                        "prompt_tokens": 1_000_010,
                        "completion_tokens": 10,
                        "total_tokens": 1_000_020,
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
                    task="planning-possible",
                    channel="filesystem",
                    seconds=4,
                    entry_window_seconds=3,
                    model="scripted-software-fixture",
                    served_model="served-fixture-alias",
                    revision="fixture",
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    key_file=None,
                    out=out,
                )
                with patch.object(checkpoint, "INTERVAL_SECONDS", 5), patch.object(checkpoint, "COHORT_SECONDS", 15):
                    self.assertEqual(asyncio.run(collect(args)), 0)
                summary = json.loads((out / "summary.json").read_text())
                self.assertEqual(
                    source_digest(out / "code"),
                    json.loads((out / "registration.json").read_text())[
                        "source_sha256"
                    ],
                )
                self.assertEqual(set(summary["finished"].values()), {"cohort_deadline"})
                self.assertGreater(summary["research_seconds"], args.seconds)
                self.assertEqual(len(summary["finished"]), 4)
                self.assertTrue(summary["physical_stop_verified"])
                self.assertEqual(summary["reason"], "cohort_deadline")
                self.assertEqual(summary["research_seconds"], 15)
                self.assertEqual(set(summary["structure_reviews"]), {"5", "10", "15"})
                self.assertEqual(summary["structure_reviews"]["15"], "no_match")
                self.assertGreater(len(observed), 8)
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
                    activation = next(e for e in events if e["kind"] == "participant_activated")
                    self.assertEqual(activation["planned_offset_seconds"], int(actor[-2:]) - 1)
                    self.assertGreaterEqual(activation["s"], activation["planned_offset_seconds"])
                    requests = [e["body"]["messages"] for e in events if e["kind"] == "request"]
                    self.assertIn('"responses": 64', requests[0][-1]["content"])
                    balance = json.loads(requests[1][-1]["content"])["your_remaining_allowance"]
                    self.assertEqual(balance, {"responses": 63, "tools": 191, "tokens": 0})
                    self.assertGreaterEqual(sum(e["kind"] == "tool_result" for e in events), 2)
                    self.assertTrue(any(e["kind"] == "research_continuation" for e in events))
                self.assertEqual(len(throttled), 1)
                self.assertGreaterEqual(sum(request == throttled[0] for _, request in observed), 2)
                retries = []
                for path in out.glob("Research*.jsonl.gz"):
                    with gzip.open(path, "rt") as log:
                        events = [json.loads(line) for line in log]
                    for i, event in enumerate(events):
                        if event["kind"] == "provider_retry":
                            retries.append(event)
                            self.assertEqual(events[i-1]["body"], events[i+1]["body"])
                            self.assertEqual(events[i+1]["attempt"], 2)
                self.assertEqual([event["status"] for event in retries], [429])
                manifest = json.loads((out / "evidence-manifest.json").read_text())
                for name, expected in manifest.items():
                    self.assertEqual(
                        hashlib.sha256((out / name).read_bytes()).hexdigest(), expected
                    )

                async def escaped_failure(self, actor):
                    raise OSError("uncaught participant exit")

                args.out = Path(directory) / "failed-participants"
                args.population = 2
                with patch(
                    "swarmform.__main__.Cohort.participant", new=escaped_failure
                ):
                    self.assertEqual(asyncio.run(collect(args)), 1)
                failed = json.loads((args.out / "summary.json").read_text())
                self.assertFalse(failed["complete"])
                self.assertTrue(failed["physical_stop_verified"])
                self.assertEqual(len(failed["errors"]), 2)
                self.assertTrue(
                    all(
                        "uncaught participant exit" in error
                        for error in failed["errors"].values()
                    )
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

        for family in ("tree", "planning"):
            with self.subTest(family=family), TemporaryDirectory() as directory:
                visible, _, _ = inputs.build_intended(
                    family + "-distributed", 3
                )
                station = CommonWorkspace(
                    visible["startup"],
                    {"population": 3},
                    observation_archive=Path(directory) / "reads",
                )
                try:
                    accounts = station.stations
                    for actor, sender in accounts.items():
                        for recipient in accounts:
                            if actor == recipient:
                                continue
                            body = f"private-{actor}-{recipient}"
                            mid = sender.as_account(["python", "/workspace/mail.py", "send", recipient, body])
                            path = f"/var/tmp/exports/messages/{recipient}/{mid}.json"
                            self.assertIn(body, accounts[recipient].as_account(["python", "/workspace/mail.py", "inbox"]))
                            outsider = next(a for a in accounts if a not in (actor, recipient))
                            self.assertNotIn(body, accounts[outsider].as_account(["python", "/workspace/mail.py", "inbox"]))
                            accounts[outsider].as_account(["test", "!", "-r", path])
                    sender.as_account(["python", "/workspace/mail.py", "send", "all", "public-probe"])
                    for account in accounts.values():
                        self.assertIn("public-probe", account.as_account(["python", "/workspace/mail.py", "inbox"]))
                    for binding in station.bindings.values():
                        self.assertTrue(binding["initial_materials_verified"])
                        self.assertEqual(len(binding["access_control"]["denied"]), 2)
                        self.assertTrue(
                            all(
                                "/specs/" in path or "/calendars/" in path
                                for path in binding["access_control"]["denied"]
                            )
                        )
                finally:
                    station.close()

    def test_public_work_artifact_and_participant_writes_in_all_four_interfaces(self):
        from swarmform import formation_inputs as inputs
        from swarmform.formation_common import CommonWorkspace
        from swarmform.formation_deployment import deployment
        from review_socket import contact

        for channel in ("direct", *inputs.CHANNELS):
            with self.subTest(channel=channel), TemporaryDirectory() as tmp:
                visible, _, manifest = (inputs.build_intended("tree-distributed", 3) if channel == "direct"
                                        else inputs.build("tree-distributed", channel, 3))
                reg = {"channel_family": manifest["channel_family"], "population": 3,
                       "deployment": {"shared": True}, "project_artifacts": visible["project_artifacts"]}
                station = (CommonWorkspace if channel == "direct" else deployment)(
                    visible["startup"], reg, observation_archive=Path(tmp) / "reads")
                try:
                    actors = list(station.stations)
                    file_interface = channel in ("direct", "filesystem")
                    seed = "tree_cli.py"
                    expected = manifest["initial_project_sha256"][seed]
                    for actor in actors:
                        command = (f"sha256sum {inputs.PROJECT}/{seed}" if file_interface else
                                   f"python /workspace/projects.py read {seed}")
                        result, _ = station.execute(actor, command)
                        self.assertEqual(result["exit_code"], 0, result)
                        self.assertIn(expected, result["stdout"])
                    local, _ = station.execute(actors[0], "printf 'local-draft' > /workspace/candidate.py && "
                                               "python /workspace/submit.py /workspace/candidate.py")
                    self.assertEqual(local["exit_code"], 0, local)
                    self.assertTrue(json.loads(local["stdout"])["local_source_coverage"]["missing"])
                    selected, _ = station.execute(actors[1], "test ! -e /workspace/output/tree_cli.py && "
                                                  "python /workspace/submit.py project:tree_cli.py && "
                                                  "sha256sum /workspace/output/tree_cli.py")
                    self.assertEqual(selected["exit_code"], 0, selected)
                    self.assertIn(expected, selected["stdout"])
                    preview, _ = station.execute(actors[1], "python /workspace/release_check.py /workspace/output/tree_cli.py "
                                                 "--keep trial-builds/candidate.py")
                    self.assertEqual(preview["exit_code"], 0, preview)
                    record = json.loads(preview["stdout"])
                    self.assertEqual(record["retained"]["sha256"], expected)
                    self.assertTrue(record["missing"])
                    self.assertEqual(record["project_build"]["current_bytes"], record["project_build"]["starter_bytes"])
                    self.assertEqual(len(record["missing"]) + len(record["present"]), 4)
                    picked, _ = station.execute(actors[2], "python /workspace/submit.py project:trial-builds/candidate.py")
                    self.assertEqual(picked["exit_code"], 0, picked)
                    self.assertIn(expected, picked["stdout"])
                    tested, _ = station.execute(actors[2], "python /workspace/release_check.py project:trial-builds/candidate.py")
                    self.assertEqual(tested["exit_code"], 0, tested)
                    self.assertEqual(json.loads(tested["stdout"].splitlines()[-1])["candidate_sha256"], expected)
                    assessment, _ = station.execute(actors[0], "python /workspace/submit.py --assessment "
                                                    "project:compatibility-assessment.json && "
                                                    "python /workspace/release_check.py --assessment /workspace/output/review.json")
                    self.assertEqual(assessment["exit_code"], 0, assessment)
                    assessed = json.loads(assessment["stdout"].splitlines()[-1])
                    self.assertIsNone(assessed["reported_feasible"])
                    self.assertEqual(assessed["reported_commands"], [])
                    self.assertEqual(assessed["project_assessment"]["name"], "compatibility-assessment.json")
                    original, _ = station.execute(actors[0], "cat /workspace/output/tree_cli.py")
                    self.assertEqual(original["stdout"], "local-draft")
                    for i, author in enumerate(actors):
                        name = f"trial-{i}.txt"
                        write = (f"printf 'domain revision' > {inputs.PROJECT}/{name}" if file_interface else
                                 f"printf 'revision {i}' > /tmp/trial; python /workspace/projects.py write {name} /tmp/trial")
                        result, _ = station.execute(author, write)
                        self.assertEqual(result["exit_code"], 0, result)
                        for reader in actors:
                            if reader == author:
                                continue
                            command = (f"cat {inputs.PROJECT}/{name}" if file_interface else
                                       f"python /workspace/projects.py read {name}")
                            result, _ = station.execute(reader, command)
                            self.assertEqual(result["exit_code"], 0, result)
                            self.assertIn("revision", result["stdout"])
                finally:
                    station.close()
                if channel == "socket":
                    audit = contact(station.terminal_service)
                    self.assertEqual(audit["peer_edges"], [(a,b) for a in actors for b in actors if a != b])
                    self.assertTrue(all(e["name"].startswith("trial-") for e in audit["events"]))

    def test_socket_and_memory_preserve_foreign_writes_and_private_sources(self):
        from swarmform import formation_inputs as inputs
        from swarmform.formation_deployment import deployment

        for channel in ("socket", "mapped_memory"):
            with self.subTest(channel=channel), TemporaryDirectory() as directory:
                visible, _, _ = inputs.build(
                    "planning-distributed", channel, 2
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
                    if channel == "mapped_memory":
                        with patch(
                            "swarmform.formation_deployment.atomic_json",
                            side_effect=OSError("simulated full disk"),
                        ):
                            with self.assertRaisesRegex(OSError, "simulated full disk"):
                                instance.close()
                        self.assertFalse(instance.closed)
                        self.assertTrue(
                            all(not s.closed for s in instance.stations.values())
                        )
                        subprocess.run(
                            ["docker", "inspect", instance.anchor],
                            check=True,
                            capture_output=True,
                        )
                        self.assertIsNone(instance.terminal_service)
                        from swarmform.participant_stop import ParticipantStop

                        stopper = ParticipantStop(instance)
                        stopper.arm()
                        stop = stopper.stop(reason="offline_recovery_test")
                        self.assertTrue(stop["research_stop_verified"])
                        original = Path(directory).resolve()
                        (original / "physical-stop.json").write_text(json.dumps(stop))
                        bindings = {
                            "memory_anchor": instance.anchor,
                            "participants": {
                                a: {
                                    "container": station.name,
                                    "account_view": getattr(
                                        station, "account_view", []
                                    ),
                                    "business_uid": station.business_uid,
                                    "observation_roots": station.observation_roots,
                                    "archive": str(
                                        station.archive.relative_to(original)
                                    ),
                                }
                                for a, station in instance.stations.items()
                            },
                        }
                        (original / "recovery-bindings.json").write_text(
                            json.dumps(bindings)
                        )
                        with TemporaryDirectory() as restored:
                            recovered = Path(restored) / "result"
                            recovery = subprocess.run(
                                [
                                    sys.executable,
                                    str(
                                        Path(__file__).resolve().parents[1]
                                        / "recover.py"
                                    ),
                                    "--run",
                                    str(original),
                                    "--out",
                                    str(recovered),
                                ],
                                capture_output=True,
                                text=True,
                            )
                            self.assertEqual(recovery.returncode, 0, recovery.stderr)
                            self.assertTrue(
                                json.loads((recovered / "summary.json").read_text())[
                                    "complete"
                                ]
                            )
                            record = json.loads(
                                (recovered / "memory/index.json").read_text()
                            )
                            raw = gzip.decompress(
                                (recovered / "memory" / record["blob"]).read_bytes()
                            )
                            self.assertEqual(
                                hashlib.sha256(raw).hexdigest(), record["sha256"]
                            )

                        # A retry after partial teardown must keep both actors' index entries.
                        def partial_release(deployment):
                            deployment.stations[first].close()
                            raise OSError("simulated teardown failure")

                        with patch(
                            "swarmform.formation_deployment.FileDeployment.close",
                            new=partial_release,
                        ):
                            with self.assertRaisesRegex(
                                OSError, "simulated teardown failure"
                            ):
                                instance.close()
                        self.assertTrue(instance.stations[first].closed)
                finally:
                    instance.close()
                self.assertTrue(instance.closed)
                self.assertIsNotNone(instance.terminal_service)
                if channel == "mapped_memory":
                    from swarmform.formation_store import mapped_request

                    archive = Path(directory) / "reads" / "_memory"
                    index = json.loads((archive / "index.json").read_text())
                    records = list(index["memory_states"].values())
                    self.assertEqual(len(records), 2)
                    self.assertEqual(records[0], records[1])
                    self.assertEqual(len(list(archive.glob("*.gz"))), 1)
                    data = gzip.decompress((archive / records[0]["blob"]).read_bytes())
                    self.assertEqual(
                        hashlib.sha256(data).hexdigest(), records[0]["sha256"]
                    )
                    cache = Path(directory) / "restored-cache"
                    cache.write_bytes(data)
                    recovered = mapped_request(
                        {"operation": "read", "name": "probe"}, path=cache
                    )
                    self.assertEqual(
                        base64.b64decode(recovered["data"]), b"fixture payload"
                    )

    def test_tree_grading_uses_protected_answers_and_determinism(self):
        from swarmform import formation_engineering as tree
        from swarmform.artifact_runner import execute_tree_cli

        _, complete, _ = tree.build("tree-possible", 3)
        _, impossible, _ = tree.build("tree-impossible", 3)
        source = tree.compile_reference(complete)
        self.assertTrue(execute_tree_cli(source, complete["probes"])["complete"])
        partial = execute_tree_cli(source, impossible["probes"])
        self.assertFalse(partial["complete"])
        self.assertGreater(partial["correct_cases"], 0)
        self.assertLess(partial["correct_cases"], partial["total_cases"])
        self.assertEqual(partial["correct_compatible_invocations"], partial["compatible_invocations"])
        self.assertLess(partial["compatible_invocations"], len(complete["probes"]) // 2)
        answers = [row["expected"] for row in impossible["probes"]]
        alternating = (
            "import json\nrows=json.loads("
            + repr(json.dumps(answers))
            + ")\ndef run(argv, stdin):\n return rows.pop(0)\n"
        )
        forged = execute_tree_cli(alternating, impossible["probes"])
        self.assertEqual(forged["correct_cases"], forged["total_cases"])
        self.assertFalse(forged["complete"])
        self.assertFalse(forged["deterministic_on_repeated_cases"])


if __name__ == "__main__":
    unittest.main()
