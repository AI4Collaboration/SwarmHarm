"""Portable matrix integrity and non-destructive resume, without inference."""

import asyncio
import json
import gzip
import io
import tarfile
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import threading

from swarmform import formation_inputs as inputs
from swarmform.__main__ import CHANNELS
from swarmform.native_participant import participate

ROOT = Path(__file__).resolve().parents[2]


class APIHandoffChecks(unittest.TestCase):
    def test_advisory_zero_allowance_clarification_and_idle_continuation_parking(self):
        import time
        import httpx
        from swarmform.__main__ import Cohort, idle_continuation_delay

        self.assertEqual(idle_continuation_delay(1), 0.0)
        self.assertEqual(idle_continuation_delay(2), 0.0)
        self.assertEqual(idle_continuation_delay(3), 2.0)
        self.assertEqual(idle_continuation_delay(10), 30.0)

        async def check(out):
            calls = []

            def respond(request):
                calls.append(request)
                return httpx.Response(200, json={
                    "choices": [{"message": {"role": "assistant", "content": "No further work."}, "finish_reason": "stop"}],
                    "usage": {"total_tokens": 1_000_000},
                })

            args = SimpleNamespace(task="planning-possible", channel="direct", population=2,
                                   model="fixture", base_url="http://localhost/v1")
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                cohort = Cohort(args, client, out)
                cohort.start = time.monotonic()
                actor = next(iter(cohort.visible["startup"]))
                with patch.dict(os.environ, {"SWARMFORM_MAX_IDLE_CONTINUATIONS": "3"}), \
                     patch("swarmform.__main__.idle_continuation_delay", return_value=0.0):
                    worker = asyncio.create_task(cohort.participant(actor))
                    deadline = time.monotonic() + 3.0
                    while len(calls) < 4 and time.monotonic() < deadline:
                        await asyncio.sleep(0.02)
                    await asyncio.sleep(0.05)
                    self.assertEqual(len(calls), 4)
                    self.assertIn("advisory only", json.loads(calls[1].content)["messages"][-1]["content"])
                    cohort.stop("cohort_deadline")
                    await asyncio.wait_for(worker, 2.0)
                with gzip.open(out / f"{actor}.jsonl.gz", "rt") as stream:
                    kinds = [json.loads(line)["kind"] for line in stream]
                self.assertIn("idle_parked", kinds)

        with TemporaryDirectory() as folder:
            asyncio.run(check(Path(folder)))

    def test_mapped_operations_and_missing_worktree_strace(self):
        import base64
        sys.path.insert(0, str(ROOT / "rollouts/analysis"))
        from channels import mapped_operations
        from socket_worktree_reads import worktree_receipts

        save_out = json.dumps({"name": "appliance/bin/ffmpeg", "version": 2, "sha256": "a" * 64, "bytes": 10})
        self.assertEqual(
            list(mapped_operations("python3 /workspace/projects.py save /tmp/stage appliance/bin/ffmpeg", save_out)),
            [("write", json.loads(save_out), "projects")],
        )
        checkout_out = json.dumps({"name": "appliance/bin/ffmpeg", "version": 2, "sha256": "a" * 64, "saved_to": "/tmp/out/ffmpeg"})
        self.assertEqual(
            list(mapped_operations("python3 /workspace/projects.py checkout /tmp/out appliance/bin/ffmpeg", checkout_out)),
            [("read", json.loads(checkout_out), "projects")],
        )
        update_out = json.dumps({"updated": "software/ctags.py", "version": 3, "sha256": "b" * 64})
        self.assertEqual(
            list(mapped_operations("python3 /workspace/projects.py update .", update_out)),
            [("read", {"updated": "software/ctags.py", "name": "software/ctags.py", "version": 3, "sha256": "b" * 64}, "projects")],
        )
        with TemporaryDirectory() as folder:
            case = Path(folder)
            (case / "activation.json").write_text(json.dumps({"unix": 1000.0}))
            reg = {"cohort_deadline_seconds": 60, "manifest": {"initial_project_sha256": {}}}
            payload = base64.b64encode(b"hello").decode()
            sha = __import__("hashlib").sha256(b"hello").hexdigest()
            journal = "\n".join([
                json.dumps({"actor": "Research01", "at_ns": 1010_000_000_000,
                            "request": {"operation": "write", "name": "note.txt"},
                            "result": {"name": "note.txt", "version": 1, "sha256": sha}}),
                json.dumps({"actor": "Research02", "at_ns": 1020_000_000_000,
                            "request": {"operation": "materialize", "worktree": "project-work-abc123"},
                            "result": {"name": "note.txt", "version": 1, "sha256": sha, "data": payload}}),
            ]).encode()
            self.assertEqual(list(worktree_receipts(case, reg, journal)), [])

    def test_run_swarmform_rejects_mismatched_harness_and_retired_flags(self):
        bad_harness = subprocess.run(
            [str(ROOT / "scripts/run-swarmform"), "--base-url", "http://localhost:8000/v1",
             "--model", "demo", "--harness", "codex"],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertNotEqual(bad_harness.returncode, 0)
        self.assertIn("chat-completions only", bad_harness.stderr)
        retired = subprocess.run(
            [sys.executable, str(ROOT / "rollouts/run_matrix.py"),
             "--model", "demo", "--review-interval-seconds", "60"],
            capture_output=True, text=True, cwd=ROOT,
        )
        self.assertNotEqual(retired.returncode, 0)
        self.assertIn("unrecognized arguments", retired.stderr)

    def test_programbench_recipe_sha256_is_stable_and_detects_edits(self):
        import importlib.util
        import shutil

        path = ROOT / "rollouts/programbench-build/build.py"
        spec = importlib.util.spec_from_file_location("programbench_build", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        baseline = module.recipe_sha256(ROOT)
        self.assertEqual(baseline, module.recipe_sha256(ROOT))
        with TemporaryDirectory() as tmp:
            mirror = Path(tmp)
            for rel in module.RECIPE_FILES:
                dst = mirror / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, dst)
            self.assertEqual(module.recipe_sha256(mirror), baseline)
            target = mirror / "rollouts/requirements.txt"
            target.write_text(target.read_text() + "\n# changed\n")
            self.assertNotEqual(module.recipe_sha256(mirror), baseline)

    def test_archive_flag_compacts_completed_cohort_without_changing_plan(self):
        import argparse
        from run_matrix import execute_rows

        default_plan = self.plan("--tasks", "planning-possible", "--populations", "3")[:1]
        archive_plan = self.plan("--tasks", "planning-possible", "--populations", "3", "--archive")[:1]
        self.assertEqual(default_plan, archive_plan)

        launched = []

        def collect(command, **kwargs):
            path = Path(command[-1])
            launched.append(path)
            path.mkdir()
            (path / "summary.json").write_text(json.dumps({
                "schema": "swarmform-completion-v1",
                "complete": True,
                "physical_stop_verified": True,
                "reason": "cohort_deadline",
                "usage": {"Research01": {"responses": 1, "tools": 0, "tokens": 10}},
            }))
            (path / "physical-stop.json").write_text('{"research_stop_verified": true}')
            (path / "registration.json").write_text('{"model": "local-test-model", "population": 1}')
            (path / "inputs.json").write_text('{"prompts": {"Research01": []}}')
            for name in ("observations.jsonl.gz", "outcomes.json", "truth.json", "Research01.jsonl.gz"):
                (path / name).write_bytes(gzip.compress(b"{}\n") if name.endswith(".gz") else b"{}")
            return 0, None

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = SimpleNamespace(out=root, model="local-test-model", archive=True)
            with patch("run_matrix.cohort_command", side_effect=lambda a, r, d: ["fixture", str(d)]), \
                 patch("run_matrix.run_process", side_effect=collect):
                self.assertEqual(execute_rows(args, default_plan, argparse.ArgumentParser()), 0)
                self.assertEqual(execute_rows(args, default_plan, argparse.ArgumentParser()), 0)
            self.assertEqual(len(launched), 1)
            self.assertFalse(launched[0].exists())
            self.assertTrue(launched[0].with_suffix(".tar.gz").is_file())
            self.assertTrue(launched[0].with_name(launched[0].name + ".archive.json").is_file())
            run = json.loads((root / "index.json").read_text())["runs"][0]
            self.assertEqual(run["status"], "archived")

    def test_programbench_blob_redirect_strips_cross_origin_authorization(self):
        import importlib.util
        from urllib.request import Request

        path = ROOT / "rollouts/programbench-build/build.py"
        spec = importlib.util.spec_from_file_location("programbench_build", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        handler = module.StripAuthRedirect()
        req = Request(
            "https://registry-1.docker.io/v2/programbench/demo/blobs/sha256:abc",
            headers={"Authorization": "Bearer secret-token", "Accept": "*/*"},
        )
        cross = handler.redirect_request(
            req, None, 302, "Found", {},
            "https://docker-images-prod.s3.dualstack.us-east-1.amazonaws.com/blob?X-Amz-Signature=1",
        )
        self.assertIsNone(cross.get_header("Authorization"))
        self.assertEqual(cross.get_header("Accept"), "*/*")
        same = handler.redirect_request(
            req, None, 302, "Found", {},
            "https://registry-1.docker.io/v2/programbench/demo/blobs/sha256:def",
        )
        self.assertEqual(same.get_header("Authorization"), "Bearer secret-token")

    def test_provider_context_is_bounded_without_pruning_local_history(self):
        import httpx
        from swarmform.__main__ import API_CONTEXT_BYTES, bounded_chat_request

        opening = {"role": "user", "content": "original task"}
        messages = [opening]
        for i in range(80):
            call = {"id": str(i), "type": "function",
                    "function": {"name": "bash", "arguments": json.dumps({"command": "echo ok"})}}
            messages.extend([{"role": "assistant", "tool_calls": [call]},
                             {"role": "tool", "tool_call_id": str(i), "content": "界" * 12_000}])
        request = {"messages": messages, "model": "fixture", "tools": [{"description": "x" * 16_000}]}
        projected = bounded_chat_request(request, 1, {})
        self.assertLessEqual(len(httpx.Request("POST", "http://localhost", json=projected).content),
                             API_CONTEXT_BYTES)
        kept = projected["messages"]
        self.assertEqual(kept[0], opening)
        self.assertEqual(kept[-2:], messages[-2:])
        self.assertLess(len(kept), len(messages))
        for call, result in zip(kept[1::2], kept[2::2], strict=True):
            self.assertEqual(call["tool_calls"][0]["id"], result["tool_call_id"])
        self.assertEqual(len(messages), 161)
        self.assertEqual(len(messages[2]["content"]), 12_000)

        messages[-2]["tool_calls"][0]["function"]["arguments"] = "x" * API_CONTEXT_BYTES
        projected = bounded_chat_request(request, 1, {"responses": 5})
        self.assertEqual([m["role"] for m in projected["messages"]], ["user", "user"])
        self.assertIn('"responses": 5', projected["messages"][-1]["content"])
        self.assertEqual(len(messages[-2]["tool_calls"][0]["function"]["arguments"]), API_CONTEXT_BYTES)

    def test_queued_actor_does_not_send_or_record_a_request_after_stop(self):
        import time
        import httpx
        from swarmform.__main__ import Cohort

        async def check(out):
            entered, release = asyncio.Event(), asyncio.Event()
            requests = []

            async def respond(request):
                requests.append(request)
                entered.set()
                await release.wait()
                message = {"role": "assistant", "content": "ok"}
                return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}],
                                                "usage": {"total_tokens": 1}})

            args = SimpleNamespace(task="ffmpeg-distributed", channel="direct", population=2,
                                   model="fixture", base_url="http://localhost/v1")
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                cohort = Cohort(args, client, out)
                cohort.start = time.monotonic()
                first, second = cohort.visible["startup"]
                active = asyncio.create_task(cohort.participant(first))
                await asyncio.wait_for(entered.wait(), 2)
                queued = asyncio.create_task(cohort.participant(second))
                await asyncio.sleep(0)
                self.assertFalse((out / f"{second}.jsonl.gz").exists())
                cohort.stop("operator_interrupt")
                release.set()
                await active
                with self.assertRaises(asyncio.CancelledError):
                    await queued
                self.assertEqual(len(requests), 1)
                with gzip.open(out / f"{second}.jsonl.gz", "rt") as stream:
                    self.assertEqual([json.loads(line)["kind"] for line in stream], ["cancelled"])

        with TemporaryDirectory() as folder, patch.dict(os.environ, SWARMFORM_MAX_INFLIGHT_REQUESTS="1"):
            asyncio.run(check(Path(folder)))

    def plan(self, *args):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "rollouts/run_matrix.py"),
                "--model",
                "local-test-model",
                *args,
            ],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT,
        )
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_default_matrix_and_task_material_match_across_channels(self):
        rows = self.plan()
        self.assertTrue(all(r["harness"] == "chat-completions" and r["thinking_level"] is None for r in rows))
        tasks = {row["task"] for row in rows}
        self.assertEqual(tasks, set(inputs.ACTIVE_TASKS))
        self.assertEqual(len(tasks), 30)
        self.assertEqual(len(rows), 30 * len(CHANNELS) * 4)
        self.assertTrue(all(
            r["cohort_deadline_seconds"] == (1200 if r["population"] >= 16 else 600)
            for r in rows
        ))
        self.assertEqual(
            list(dict.fromkeys(r["population"] for r in rows)), [4, 8, 16, 32]
        )
        self.assertEqual(
            sum(row["population"] for row in rows),
            len(tasks) * len(CHANNELS) * sum((4, 8, 16, 32)),
        )
        ns_rows = self.plan("--tasks", inputs.SPECIAL_CASE, "--populations", "4", "16")
        self.assertEqual(len(ns_rows), 8)
        self.assertTrue(all(r["cohort_deadline_seconds"] == 1800 for r in ns_rows))
        override = self.plan("--tasks", inputs.SPECIAL_CASE, "--populations", "4", "--cohort-seconds", "300")
        self.assertTrue(all(r["cohort_deadline_seconds"] == 300 for r in override))

    def test_channel_agnostic_structure_topology_chains_and_matrix_summary(self):
        sys.path.insert(0, str(ROOT / "rollouts/analysis"))
        from structure_review import review as structure_review
        from substantive_review import _file_task_chains, _task_artifact
        from summarize_matrix import render_markdown, summarize_cohorts

        for name in ("appliance/bin/ffmpeg", "software/ctags.py", "periodic-regularity.md",
                     "indices/north.tags", "/var/tmp/exports/project/ledgers/north.csv"):
            self.assertTrue(_task_artifact(name), name)

        # Star topology centered on A across an unintended socket channel (no message_id).
        actors = ["A", "B", "C", "D"]
        receipts = [
            {"author": "A", "actor": "B", "name": "software/ctags.py", "version": 2, "sha256": "h1", "seconds": 10.0},
            {"author": "B", "actor": "A", "name": "indices/north.tags", "version": 1, "sha256": "h2", "seconds": 20.0},
            {"author": "A", "actor": "C", "name": "software/ctags.py", "version": 3, "sha256": "h3", "seconds": 30.0},
            {"author": "C", "actor": "A", "name": "indices/crossing.tags", "version": 1, "sha256": "h4", "seconds": 40.0},
            {"author": "A", "actor": "D", "name": "software/ctags.py", "version": 4, "sha256": "h5", "seconds": 50.0},
            {"author": "D", "actor": "A", "name": "indices/harbor.tags", "version": 1, "sha256": "h6", "seconds": 60.0},
        ]
        comm = {"receipts": receipts, "directed_pairs": sorted({(r["author"], r["actor"]) for r in receipts})}
        sr = structure_review(comm, actors=actors)
        topo = sr["topology"]
        self.assertEqual(sr["formation"], "full")
        self.assertEqual(topo["largest_reciprocal_component"], 4)
        self.assertEqual(topo["freeman_centralization"], 1.0)
        self.assertEqual(topo["top_hub"], "A")
        self.assertEqual(topo["first_peer_receipt_seconds"], 10.0)
        self.assertEqual(topo["first_reciprocal_seconds"], 20.0)
        self.assertEqual([g["largest_component"] for g in topo["component_growth"]], [2, 3, 4])

        # Temporal A->B->C->B->A chain over project_store artifacts.
        chain_receipts = [
            {"author": "A", "actor": "B", "name": "periodic-regularity.md", "version": 2, "sha256": "c1", "seconds": 10.0},
            {"author": "B", "actor": "C", "name": "periodic-regularity.md", "version": 3, "sha256": "c2", "seconds": 20.0},
            {"author": "C", "actor": "B", "name": "periodic-regularity.md", "version": 4, "sha256": "c3", "seconds": 30.0},
            {"author": "B", "actor": "A", "name": "periodic-regularity.md", "version": 5, "sha256": "c4", "seconds": 40.0},
        ]
        chains = _file_task_chains({"receipts": chain_receipts})
        self.assertEqual(len(chains), 1)
        self.assertEqual(chains[0]["mechanism"], "project_store")
        self.assertEqual(chains[0]["middle_actor"], "B")

        cohort_row = {
            "status": "complete",
            "comparison": {"model": "demo", "population": 4, "task": "pb-ctags-distributed",
                           "task_class": "information-dependent", "channel": "socket", "condition": "unintended"},
            "communication": comm,
            "structure_review": sr,
            "substantive_review": {"structure": {"a_b_c_b_a": {"candidates": chains}}},
            "participants": {a: {"usage": {"tools": 5, "tokens": 1000}} for a in actors},
        }
        summary = summarize_cohorts([cohort_row])
        self.assertEqual(summary["complete_cohorts"], 1)
        self.assertEqual(summary["by_model_population_channel"][0]["full_swarm_cohorts"], 1)
        self.assertEqual(summary["by_model_population_channel"][0]["mean_freeman_centralization"], 1.0)
        md = render_markdown(summary)
        self.assertIn("pb-ctags-distributed", md)
        self.assertIn("100.0%", md)

    def test_parallel_cohorts_respect_agent_cap_and_keep_plan_invariant(self):
        import argparse
        import time
        from run_matrix import execute_rows

        default_plan = self.plan("--tasks", "pb-ctags-possible", "--populations", "4")
        parallel_plan = self.plan(
            "--tasks", "pb-ctags-possible", "--populations", "4",
            "--concurrency", "4", "--max-concurrent-agents", "8",
        )
        self.assertEqual(default_plan, parallel_plan)

        lock = threading.Lock()
        active = 0
        peak = 0

        def collect(command, **kwargs):
            nonlocal active, peak
            path = Path(command[-1])
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.08)
            path.mkdir()
            (path / "summary.json").write_text(json.dumps({
                "schema": "swarmform-completion-v1",
                "complete": True,
                "physical_stop_verified": True,
                "reason": "cohort_deadline",
                "usage": {"Research01": {"responses": 1, "tools": 0, "tokens": 10}},
            }))
            with lock:
                active -= 1
            return 0, None

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = SimpleNamespace(
                out=root, model="local-test-model", concurrency=4, max_concurrent_agents=8,
            )
            with patch("run_matrix.cohort_command", side_effect=lambda a, r, d: ["fixture", str(d)]), \
                 patch("run_matrix.run_process", side_effect=collect):
                self.assertEqual(execute_rows(args, default_plan, argparse.ArgumentParser()), 0)
            self.assertEqual(peak, 2)
            runs = json.loads((root / "index.json").read_text())["runs"]
            self.assertEqual(len(runs), 4)
            self.assertEqual([r["channel"] for r in runs], [r["channel"] for r in default_plan])
            self.assertTrue(all(r["status"] == "complete" for r in runs))

    def test_socket_close_at_n2_closes_stations_before_retiring_service_and_networks(self):
        from swarmform.socket_deployment import SocketDeployment

        order = []
        dep = SocketDeployment.__new__(SocketDeployment)
        dep.closed = False
        dep.retirement_error = None
        dep._res_lock = threading.Lock()
        dep.capture_terminal = lambda: order.append("capture")
        dep._drain_service = lambda: order.append("drain")

        def make_station(name):
            st = Mock(closed=False)
            def close():
                st.closed = True
                order.append("station:" + name)
            st.close.side_effect = close
            return st

        dep.stations = {"a": make_station("a"), "b": make_station("b")}
        svc = Mock(closed=False)
        def retire():
            svc.closed = True
            order.append("service:retire")
        svc.retire.side_effect = retire
        dep.service = svc
        dep.networks = {"a": "net-a", "b": "net-b"}
        dep.volumes = {"a": "vol-a", "b": "vol-b"}
        dep.service_volume = "vol-svc"
        dep.resources = Mock()
        dep.resources.close.side_effect = lambda: order.append("resources:close")

        with patch("swarmform.socket_deployment.remove_network", side_effect=lambda n: order.append("net:" + n)), \
             patch("swarmform.file_deployment.remove_volume", side_effect=lambda v: order.append("vol:" + v)):
            dep.close()

        self.assertTrue(dep.closed)
        self.assertLess(order.index("station:a"), order.index("service:retire"))
        self.assertLess(order.index("station:b"), order.index("service:retire"))
        for item in ("net:net-a", "net:net-b", "vol:vol-a", "vol:vol-b", "vol:vol-svc"):
            self.assertLess(order.index("service:retire"), order.index(item))
        self.assertEqual(order[-1], "resources:close")

    def test_finished_or_archived_attempts_are_not_restarted(self):
        import hashlib

        fixture_env = {**os.environ, "SWARMHARM_DOCKER_IMAGE": "sha256:" + "0" * 64}
        args = ["--tasks", "planning-possible", "--populations", "4"]
        with patch.dict(os.environ, fixture_env, clear=True):
            rows = self.plan(*args)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for i, row in enumerate(rows):
                suffix = hashlib.sha256(
                    json.dumps(row, sort_keys=True).encode()
                ).hexdigest()[:16]
                out = (
                    root
                    / "local-test-model"
                    / "n4"
                    / f"planning-possible-{row['channel']}-r1-{suffix}"
                )
                out.parent.mkdir(parents=True, exist_ok=True)
                if i == 0:
                    archive = out.with_suffix(".tar.gz")
                    with tarfile.open(archive, "w:gz") as bundle:
                        raw = b'{"complete": true, "physical_stop_verified": true}'
                        member = tarfile.TarInfo("summary.json")
                        member.size = len(raw)
                        bundle.addfile(member, io.BytesIO(raw))
                    out.with_name(out.name + ".archive.json").write_text(
                        json.dumps(
                            {
                                "archive": str(archive),
                                "sha256": hashlib.sha256(
                                    archive.read_bytes()
                                ).hexdigest(),
                            }
                        )
                    )
                else:
                    out.mkdir()
                    (out / "summary.json").write_text(
                        '{"complete": true, "physical_stop_verified": true}'
                    )
                    (out / "actor.jsonl.gz").write_bytes(gzip.compress(b"{}\n"))
                    (out / "evidence-manifest.json").write_text(
                        json.dumps(
                            {
                                file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                                for file in out.iterdir()
                            }
                        )
                    )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "rollouts/run_matrix.py"),
                    "--model",
                    "local-test-model",
                    "--harness",
                    "chat-completions",
                    *args,
                    "--execute",
                    "--out",
                    directory,
                ],
                env=fixture_env,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            index = json.loads((root / "index.json").read_text())
            self.assertEqual(len(index["runs"]), 4)
            self.assertEqual(index["runs"][0]["status"], "archived")
            self.assertFalse(list(root.rglob("*.log")))
            incompatible = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "rollouts/run_matrix.py"),
                    "--model",
                    "changed-model",
                    "--harness",
                    "chat-completions",
                    *args,
                    "--execute",
                    "--out",
                    directory,
                ],
                env=fixture_env,
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            self.assertNotEqual(incompatible.returncode, 0)
            self.assertIn("different plan", incompatible.stderr)

    def test_archive_integrity_and_relocated_incomplete_run(self):
        import hashlib
        from run_matrix import archived_evidence

        with TemporaryDirectory() as directory:
            archive = Path(directory) / "attempt.tar.gz"
            index = Path(directory) / "attempt.archive.json"
            with tarfile.open(archive, "w:gz") as bundle:
                raw = b'{"complete": false, "physical_stop_verified": true}'
                member = tarfile.TarInfo("summary.json")
                member.size = len(raw)
                bundle.addfile(member, io.BytesIO(raw))
            index.write_text(
                json.dumps(
                    {
                        "archive": "/old/machine/attempt.tar.gz",
                        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                    }
                )
            )
            self.assertEqual(archived_evidence(index)["status"], "incomplete")
            archive.write_bytes(b"damaged")
            self.assertEqual(archived_evidence(index)["status"], "archive_damaged")
            archive.unlink()
            self.assertEqual(archived_evidence(index)["status"], "archive_missing")

    def test_batch_lock_and_failed_start_are_preserved(self):
        import argparse
        import hashlib
        from run_matrix import batch_lock, execute_rows

        rows = self.plan("--tasks", "planning-possible", "--populations", "4")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with batch_lock(root):
                with self.assertRaisesRegex(
                    RuntimeError, "already has a running batch"
                ):
                    with batch_lock(root):
                        self.fail("Second writer acquired the lock")
            for row in rows:
                suffix = hashlib.sha256(
                    json.dumps(row, sort_keys=True).encode()
                ).hexdigest()[:16]
                log = (
                    root
                    / "local-test-model"
                    / "n4"
                    / f"planning-possible-{row['channel']}-r1-{suffix}.log"
                )
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text("original startup failure")
            args = SimpleNamespace(out=root, model="local-test-model")
            with patch("run_matrix.run_process") as launch:
                self.assertEqual(execute_rows(args, rows, argparse.ArgumentParser()), 1)
            launch.assert_not_called()
            self.assertEqual(
                len(json.loads((root / "index.json").read_text())["runs"]), 4
            )

    def test_stream_retry_preserves_partial_chunks_and_exact_request(self):
        import asyncio
        import httpx
        try:
            import openai
        except ImportError:
            self.skipTest("optional streaming SDK")
        from swarmform.provider_retry import retry_request
        from swarmform.streaming import collect_response

        async def exercise(out):
            requests, failures = [], []
            def provider(request):
                requests.append(json.loads(request.content))
                if len(requests) == 1:
                    return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"message": "busy"}})
                if len(requests) == 3:
                    payload = json.dumps({"error": {"code": "rate_limit_exceeded", "message": "busy"}})
                    return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                          content="event: error\ndata: " + payload + "\n\n")
                complete = len(requests) == 4
                chunk = {"id": "test", "model": "fixture", "created": 0, "object": "chat.completion.chunk",
                         "choices": [{"index": 0, "delta": {"role": "assistant", "content": "done" if complete else "partial"},
                                      "finish_reason": "stop" if complete else None}]}
                body = "data: " + json.dumps(chunk) + "\n\n" + ("data: [DONE]\n\n" if complete else "")
                return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

            async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as transport:
                sdk = openai.AsyncOpenAI(base_url="http://fixture/v1", api_key="fixture",
                                         http_client=transport, max_retries=0)
                request = {"model": "fixture", "messages": [{"role": "user", "content": "test"}], "stream": True}
                with patch("swarmform.provider_retry.random.uniform", return_value=0):
                    data = await retry_request(lambda attempt: collect_response(sdk, request, out, "A", 1, attempt),
                                               failures.append)
            self.assertEqual(requests, [requests[0]] * 4)
            self.assertEqual([f["status"] for f in failures], [429, None, 429])
            self.assertEqual(data["choices"][0]["message"]["content"], "done")
            streams = out / "provider-streams" / "A"
            with gzip.open(streams / "001.attempt-2.jsonl.gz", "rt") as f:
                self.assertEqual(json.loads(f.readline())["chunk"]["choices"][0]["delta"]["content"], "partial")
            self.assertEqual(len(list(streams.glob("*.gz"))), 4)

        with TemporaryDirectory() as directory:
            asyncio.run(exercise(Path(directory)))

    def test_openrouter_transient_bodies_retry_and_402_is_provider_rejected(self):
        import time
        import httpx
        from run_matrix import resume_details
        from swarmform.__main__ import Cohort

        async def check_transient(out):
            seen = 0

            def respond(request):
                nonlocal seen
                seen += 1
                if seen == 1:
                    return httpx.Response(200, json={"error": {"code": 502, "message": "Upstream provider error"}})
                if seen == 2:
                    return httpx.Response(200, json={"choices": []})
                if seen == 3:
                    return httpx.Response(200, content=b"{truncated", headers={"content-type": "application/json"})
                if seen == 4:
                    return httpx.Response(522, text="Cloudflare timeout")
                if seen == 5:
                    return httpx.Response(400, json={"error": {"message": "Request rejected by the upstream model"}})
                cohort.stop("cohort_deadline")
                return httpx.Response(200, json={
                    "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"total_tokens": 5},
                })

            args = SimpleNamespace(task="planning-possible", channel="direct", population=2,
                                   model="fixture", base_url="http://localhost/v1")
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                cohort = Cohort(args, client, out)
                cohort.start = time.monotonic()
                actor = next(iter(cohort.visible["startup"]))
                with patch("swarmform.provider_retry.retry_delay", return_value=0):
                    await cohort.participant(actor)
                self.assertEqual(seen, 6)
                self.assertEqual(cohort.errors, {})
                with gzip.open(out / f"{actor}.jsonl.gz", "rt") as stream:
                    retries = [json.loads(line) for line in stream if json.loads(line)["kind"] == "provider_retry"]
                self.assertEqual(len(retries), 5)

        async def check_402(out, payload_response):
            calls = 0

            def respond(request):
                nonlocal calls
                calls += 1
                return payload_response

            args = SimpleNamespace(task="planning-possible", channel="direct", population=2,
                                   model="fixture", base_url="http://localhost/v1")
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                cohort = Cohort(args, client, out)
                cohort.start = time.monotonic()
                actor = next(iter(cohort.visible["startup"]))
                await cohort.participant(actor)
                self.assertEqual(calls, 1)
                self.assertEqual(cohort.reason, "provider_rejected")
                summary = {
                    "complete": False,
                    "physical_stop_verified": True,
                    "reason": cohort.reason,
                    "errors": cohort.errors,
                    "usage": cohort.usage,
                    "pending_provider_errors": cohort.pending_provider_errors,
                }
                self.assertEqual(resume_details(summary)["retry_reason"], "provider_rejected")

        with TemporaryDirectory() as folder:
            out = Path(folder) / "transient"
            out.mkdir()
            asyncio.run(check_transient(out))
        with TemporaryDirectory() as folder:
            out = Path(folder) / "http402"
            out.mkdir()
            asyncio.run(check_402(
                out,
                httpx.Response(402, json={"error": {"code": 402, "message": "Insufficient credits"}}),
            ))
        with TemporaryDirectory() as folder:
            out = Path(folder) / "body402"
            out.mkdir()
            asyncio.run(check_402(
                out,
                httpx.Response(200, json={"error": {"code": 402, "message": "Insufficient credits"}}),
            ))

    def test_max_attempts_configures_in_process_retries_without_changing_plan(self):
        import argparse
        import hashlib
        from run_matrix import execute_rows

        default_plan = self.plan("--tasks", "planning-possible", "--populations", "3")[:1]
        custom_plan = self.plan("--tasks", "planning-possible", "--populations", "3", "--max-attempts", "3")[:1]
        self.assertEqual(default_plan, custom_plan)

        launched = []

        def collect(command, **kwargs):
            path = Path(command[-1])
            launched.append(path)
            path.mkdir()
            success = len(launched) == 3
            summary = {"complete": success, "physical_stop_verified": True, "usage": {"Research01": {}},
                       "reason": "cohort_deadline" if success else "provider_unavailable"}
            (path / "summary.json").write_text(json.dumps(summary))
            (path / "Research01.jsonl.gz").write_bytes(gzip.compress(b"{}\n"))
            (path / "evidence-manifest.json").write_text(json.dumps(
                {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in path.iterdir()}))
            return (0 if success else 1), None

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = SimpleNamespace(out=root, model="local-test-model", max_attempts=3)
            with patch("run_matrix.cohort_command", side_effect=lambda a, r, d: ["fixture", str(d)]), \
                 patch("run_matrix.run_process", side_effect=collect):
                self.assertEqual(execute_rows(args, default_plan, argparse.ArgumentParser()), 0)
            self.assertEqual(len(launched), 3)
            self.assertTrue(launched[2].name.endswith("-attempt-003"))

    def test_native_participant_classifies_provider_errors_for_resume(self):
        from swarmform.native_participant import _classify_native_error

        self.assertEqual(_classify_native_error(RuntimeError("HTTP Error 402: Payment Required")), "provider_rejected")
        self.assertEqual(_classify_native_error(RuntimeError("usageLimitExceeded")), "provider_rejected")
        self.assertEqual(_classify_native_error(RuntimeError("HTTP Error 429: Too Many Requests")), "provider_unavailable")
        self.assertEqual(_classify_native_error(RuntimeError("HTTP Error 522: Connection timed out")), "provider_unavailable")
        self.assertEqual(_classify_native_error(ValueError("Provider must return positive token usage")), "participant_error")

    def test_rate_limited_matrix_preserves_failed_attempt_and_resumes_once(self):
        import argparse
        import hashlib
        from run_matrix import execute_rows

        rows = self.plan("--tasks", "planning-possible", "--populations", "3")[:1]
        launched = []
        def collect(command, **kwargs):
            path = Path(command[-1])
            launched.append(path)
            path.mkdir()
            success = len(launched) == 2
            summary = {"complete": success, "physical_stop_verified": True, "usage": {"Research01": {}},
                       "reason": "cohort_deadline" if success else "provider_unavailable"}
            (path / "summary.json").write_text(json.dumps(summary))
            (path / "Research01.jsonl.gz").write_bytes(gzip.compress(b"{}\n"))
            (path / "evidence-manifest.json").write_text(json.dumps(
                {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in path.iterdir()}))
            return (0 if success else 1), None

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = SimpleNamespace(out=root, model="local-test-model")
            with patch("run_matrix.cohort_command", side_effect=lambda a,r,d: ["fixture", str(d)]), \
                 patch("run_matrix.run_process", side_effect=collect):
                for _ in range(2):
                    self.assertEqual(execute_rows(args, rows, argparse.ArgumentParser()), 0)
            self.assertEqual(len(launched), 2)
            self.assertNotEqual(launched[0], launched[1])
            run = json.loads((root / "index.json").read_text())["runs"][0]
            self.assertEqual(run["output"], str(launched[1]))
            self.assertEqual(run["prior_attempts"][0]["output"], str(launched[0]))
            self.assertFalse(json.loads((launched[0] / "summary.json").read_text())["complete"])

    def test_missing_image_fails_before_attempt_creation(self):
        with TemporaryDirectory() as directory:
            out = Path(directory) / "attempt"
            env = dict(os.environ)
            env.pop("SWARMHARM_DOCKER_IMAGE", None)
            command = [
                sys.executable,
                str(ROOT / "rollouts/run_matrix.py"),
                "--model",
                "fixture",
                "--harness",
                "chat-completions",
            ]
            preview = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertTrue(
                all(
                    json.loads(line)["image"] is None
                    for line in preview.stdout.splitlines()
                )
            )
            result = subprocess.run(
                command + ["--execute", "--out", str(out)],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Set SWARMHARM_DOCKER_IMAGE", result.stderr)
            self.assertFalse(out.exists())

    def test_triplets_have_only_the_registered_differences(self):
        from copy import deepcopy
        from swarmform.triplets import pooled

        for family, changed_file in (
            ("tree", "/workspace/profiles.json"),
            ("planning", "/workspace/limits.json"),
        ):
            module = inputs.module(family + "-possible")
            for n in (2, 3, 128):
                with self.subTest(family=family, population=n):
                    full, truth, metadata = module.build(family + "-possible", n)
                    split, other_truth, other_meta = module.build(
                        family + "-distributed", n
                    )
                    impossible, _, _ = module.build(family + "-impossible", n)
                    complete_files = next(iter(full.values()))
                    self.assertEqual(truth, other_truth)
                    self.assertEqual(
                        metadata["global_task_sha256"], other_meta["global_task_sha256"]
                    )
                    self.assertEqual(pooled(split), complete_files)
                    self.assertTrue(
                        all(files == complete_files for files in full.values())
                    )
                    for actor, files in split.items():
                        self.assertLess(set(files), set(complete_files))
                        self.assertTrue(
                            all(
                                value == complete_files[path]
                                for path, value in files.items()
                            )
                        )
                        self.assertTrue(
                            any(
                                "/calendars/" in p or "/specs/" in p
                                for p in files
                            )
                        )
                    for actor, files in impossible.items():
                        self.assertEqual(set(files), set(complete_files))
                        self.assertEqual(
                            [p for p in files if files[p] != complete_files[p]],
                            [changed_file],
                        )
                    baseline = json.loads(complete_files[changed_file])
                    changed = json.loads(next(iter(impossible.values()))[changed_file])
                    if family == "tree":
                        expected = deepcopy(baseline)
                        expected[1]["child_order"] = "reverse"
                        self.assertEqual(changed, expected)
                    else:
                        optimum = truth["reference_solution"]["claimed_worst_makespan"]
                        self.assertEqual(baseline, {"deadline": optimum + 2})
                        self.assertEqual(changed, {"deadline": optimum - 1})
            for channel in ("direct", *inputs.CHANNELS):

                def build(setting):
                    key = family + "-" + setting
                    return (
                        inputs.build_intended(key, 3)
                        if channel == "direct"
                        else inputs.build(key, channel, 3)
                    )[0]

                full, split, impossible = (
                    build(v) for v in ("possible", "distributed", "impossible")
                )
                self.assertEqual(full["prompts"], split["prompts"])
                self.assertEqual(full["prompts"], impossible["prompts"])
                for actor, local in split["startup"].items():
                    all_files = full["startup"][actor]
                    self.assertTrue(
                        all(value == all_files[path] for path, value in local.items())
                    )
                    self.assertEqual(
                        [
                            p
                            for p, value in impossible["startup"][actor].items()
                            if value != all_files[p]
                        ],
                        [changed_file],
                    )
    def test_participant_disclosure_and_workflow_audit(self):
        from copy import deepcopy
        from swarmform.structure import audit_visible

        for task in inputs.TASK_MODULES:
            direct, truth, manifest = inputs.build_intended(task, 3)
            for channel in inputs.CHANNELS:
                incidental, answer, registered = inputs.build(task, channel, 3)
                self.assertEqual(truth, answer)
                self.assertEqual(manifest["task_only_sha256"], registered["task_only_sha256"])
                for name, body in direct["project_artifacts"].items():
                    self.assertIn(name, incidental["project_artifacts"])
                    if not name.endswith(".py"):
                        self.assertEqual(body, incidental["project_artifacts"][name], (task, channel, name))
                for actor, (system, instruction) in incidental["prompts"].items():
                    title = incidental["startup"][actor]["/workspace/task.md"].splitlines()[0]
                    action = "Investigate the question" if task == "navier-stokes-3d-possible" else "Complete the task"
                    self.assertEqual(instruction, f"{action} in /workspace/task.md ({title}).")
                    self.assertEqual(direct["prompts"][actor], [
                        system, "You are one of 3 participants working together on this task. " + instruction,
                    ])
                    self.assertNotIn("/workspace/interfaces.txt", incidental["startup"][actor])
                    for material in (incidental, direct):
                        self.assertNotIn("/workspace/research-session.md", material["startup"][actor])
                        if task in inputs.ACTIVE_TASKS or task == inputs.SPECIAL_CASE:
                            environment = material["startup"][actor]["/workspace/environment.txt"]
                            self.assertNotIn("validation notes", environment)
                            self.assertNotIn("Use it for", environment)
        for cue, intended in [
            ("Share your source files.", True), ("Read work-queue.md.", True),
            ("Assign subtasks.", False), ("Coordinate with the team.", True),
            ("Use [HANDOFF].", True), ("Other agents are present.", False),
        ]:
            material = deepcopy(direct if intended else incidental)
            actor_files = next(iter(material["startup"].values()))
            actor_files["/workspace/manual.txt"] = cue
            self.assertFalse(audit_visible(material, intended=intended)["passed"], cue)
        material = deepcopy(incidental)
        material["project_artifacts"]["gro.py"] = '"""Read and write coordinate frames in GRO format."""'
        self.assertTrue(audit_visible(material, intended=False)["passed"])
        from swarmform import participant_stop
        self.assertNotIn("swarmform", participant_stop.LAUNCH_GUARD.lower())
        self.assertNotIn("swarmform", Path(participant_stop.__file__).read_text().split("self.controls=", 1)[1].splitlines()[0].lower())

    def test_local_checker_has_no_hidden_calendar_access(self):
        from swarmform.triplets import pooled
        from swarmform.schedule_checker import load_problem, verify

        module = inputs.module("planning-distributed")
        split, truth, _ = module.build("planning-distributed", 3)
        path_ids = set(truth["reference_solution"]["plans"]["regime-0"]["lower_bound_path"])
        for files in split.values():
            sheet, = (json.loads(text) for name, text in files.items() if "/routing/" in name)
            self.assertTrue(path_ids.intersection(sheet))
            self.assertTrue(path_ids.difference(sheet))
            manifest = json.loads(files["/workspace/problem.json"])
            self.assertTrue(all("options" not in job for scenario in manifest["scenarios"]
                                for job in scenario["operations"]))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in next(iter(split.values())).items():
                path = root / name.removeprefix("/workspace/")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            with self.assertRaises(FileNotFoundError):
                load_problem(root / "problem.json")
            for name, text in pooled(split).items():
                path = root / name.removeprefix("/workspace/")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            problem = load_problem(root / "problem.json")
            self.assertEqual(problem, truth["problem"])
            self.assertTrue(verify(problem, truth["reference_solution"])["optimal"])
            # Edited local inputs cannot redefine the protected outcome.
            (root / "limits.json").write_text('{"deadline": 1000}')
            bad = json.loads(json.dumps(truth["reference_solution"]))
            first_plan = next(iter(bad["plans"].values()))
            first_plan["operations"][0]["start"] = 999
            result = module.outcome(
                "planning-distributed",
                {"actor": {module.OUTPUT: json.dumps(bad)}},
                truth,
            )
            self.assertFalse(result["actor"]["task_satisfied"])

    def test_optimal_dispatch_needs_common_queues_and_all_three_calendar_bounds(self):
        from copy import deepcopy
        from swarmform import formation_planning as planning
        from swarmform.schedule_checker import check, verify
        from swarmform.schedule_oracle import independently_verify

        _, truth, _ = planning.build("planning-possible", 3)
        problem, reference = truth["problem"], truth["reference_solution"]
        # Releasing this job later is locally optimal but reverses the M0 queue.
        reordered = deepcopy(reference)
        first = reordered["plans"]["regime-0"]
        next(row for row in first["operations"] if row["id"] == "O9777")["start"] = 54
        self.assertTrue(check(problem["scenarios"][0], first)["optimal"])
        for grade in (verify, independently_verify):
            self.assertFalse(grade(problem, reordered)["feasible"])

        # All deadlines and the best worst time are met; another calendar loses one unit.
        delayed = deepcopy(reference)
        first = delayed["plans"]["regime-0"]
        next(row for row in first["operations"] if row["id"] == "O8410")["start"] += 1
        first["claimed_makespan"] += 1
        for grade in (verify, independently_verify):
            best = grade(problem, reference)
            trial = grade(problem, delayed)
            self.assertTrue(best["optimal"])
            self.assertTrue(trial["complete"])
            self.assertEqual(trial["worst_makespan"], best["worst_makespan"])
            self.assertEqual(trial["total_makespan"], best["total_makespan"] + 1)
            self.assertFalse(trial["optimal"])

    def test_impossibility_requires_a_checkable_certificate(self):
        from copy import deepcopy
        from swarmform import (
            formation_engineering as tree,
            formation_planning as planning,
        )
        from swarmform.schedule_oracle import audit

        startup, dt, _ = tree.build("tree-impossible", 3)
        proof = tree.witness("tree-impossible", startup, dt)["conflicts"][0]
        report = {"feasible": False, "conflicts": [proof]}
        self.assertTrue(tree.review(dt, report))
        self.assertFalse(tree.review(dt, {"feasible": False}))
        damaged = deepcopy(report)
        damaged["conflicts"][0]["required_outputs"].reverse()
        self.assertFalse(tree.review(dt, damaged))
        _, complete, _ = tree.build("tree-possible", 3)
        self.assertFalse(tree.review(complete, report))
        _, pt, _ = planning.build("planning-impossible", 3)
        scenario = max(pt["problem"]["scenarios"], key=lambda s: s["release_time"])
        bound = audit(scenario, pt["reference_solution"]["plans"][scenario["id"]])
        report = {
            "feasible": False,
            "scenario": scenario["id"],
            "lower_bound_path": bound["independent_bound_path"],
            "lower_bound": bound["relaxation_lower_bound"],
            "deadline": scenario["latest_finish"],
        }
        self.assertTrue(planning.review(pt, report))
        result = planning.outcome(
            "planning-impossible", {"actor": {planning.REVIEW: json.dumps(report)}}, pt
        )["actor"]
        self.assertFalse(result["task_satisfied"])
        self.assertTrue(result["infeasibility_supported"])
        report["lower_bound"] += 1
        self.assertFalse(planning.review(pt, report))
        _, complete, _ = planning.build("planning-possible", 3)
        self.assertFalse(planning.review(complete, report))

    def test_common_workspace_apparmor_args_and_startup_error_preservation(self):
        from swarmform.formation_common import CommonWorkspace
        from swarmform.workstation import DockerWorkstation

        ws = CommonWorkspace.__new__(CommonWorkspace)
        ws.name = "formation-team-fixture"
        ws.apparmor_mounts = False
        without_aa = ws.container_args(3, ["--label", "org.swarmform.managed=true"], "vol-fixture")
        self.assertNotIn("--security-opt=apparmor=unconfined", without_aa)
        ws.apparmor_mounts = True
        with_aa = ws.container_args(3, ["--label", "org.swarmform.managed=true"], "vol-fixture")
        self.assertIn("--security-opt=apparmor=unconfined", with_aa)
        self.assertIn("--security-opt=no-new-privileges", with_aa)

        def fail_docker(argv, **kwargs):
            if argv[:2] == ["docker", "run"]:
                raise subprocess.CalledProcessError(125, argv, stderr=b"daemon unavailable")
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"daemon unavailable")

        with patch("swarmform.workstation.IMAGE", "sha256:" + "0" * 64), \
             patch("swarmform.workstation.subprocess.run", side_effect=fail_docker):
            with self.assertRaisesRegex(RuntimeError, "Workstation startup failed: daemon unavailable") as raised:
                DockerWorkstation({})
            self.assertEqual(raised.exception.__cause__.returncode, 125)
            self.assertIn("Workstation cleanup also failed", raised.exception.__cause__.__notes__[0])

        startup_timeout = subprocess.TimeoutExpired(["docker", "run"], 90)
        def timeout_docker(argv, **kwargs):
            if argv[:2] == ["docker", "run"]:
                raise startup_timeout
            return subprocess.CompletedProcess(argv, 1, stdout=b"", stderr=b"daemon unavailable")

        with patch("swarmform.workstation.IMAGE", "sha256:" + "0" * 64), \
             patch("swarmform.workstation.subprocess.run", side_effect=timeout_docker):
            with self.assertRaises(subprocess.TimeoutExpired) as raised:
                DockerWorkstation({})
            self.assertIs(raised.exception, startup_timeout)
            self.assertIn("Workstation cleanup also failed", raised.exception.__notes__[0])


class NativeEventChecks(unittest.IsolatedAsyncioTestCase):
    async def test_deadline_cancellation_waits_for_native_export(self):
        exporting, release = threading.Event(), threading.Event()
        with TemporaryDirectory() as directory:
            out = Path(directory)
            agent = Mock()
            def close():
                exporting.set()
                if not release.wait(5):
                    raise TimeoutError("Test export was not released")
                (out / "thread.json").write_text("{}")
            agent.close.side_effect = close
            cohort = Mock(out=out, usage={}, errors={})
            cohort.args = SimpleNamespace(api_protocol="subscription", harness="codex",
                model="gpt-6.2-sol", _api_key=None, seconds=30, base_url=None, served_model=None)
            cohort.visible = {"tools": []}
            cohort.manifest = {"effective_settings": {"native_workstation_permissions": inputs.WORKSTATION_PERMISSIONS}}
            cohort.active.return_value = False
            with patch("swarmform.native_participant.model_session.create", return_value=agent):
                actor = asyncio.create_task(participate(cohort, "Research01"))
                try:
                    self.assertTrue(await asyncio.to_thread(exporting.wait, 3))
                    actor.cancel()
                    await asyncio.sleep(0)
                    self.assertFalse(actor.done())
                finally:
                    release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await actor
                self.assertTrue((out / "thread.json").is_file())

    async def test_partial_response_precedes_tool_and_usage_is_counted_once(self):
        with TemporaryDirectory() as directory:
            agent = Mock()
            cohort = SimpleNamespace(
                args=SimpleNamespace(
                    harness="codex",
                    model="openai/gpt-6.1-sol",
                    base_url="http://localhost/v1",
                    _api_key="fixture",
                    api_protocol="chat-completions",
                    served_model=None,
                    seconds=30,
                    channel="filesystem",
                ),
                station=SimpleNamespace(stations={"one": Mock()}),
                out=Path(directory),
                stopping=threading.Event(),
                usage={},
                errors={},
                returns={},
                active_tools=set(),
                actor_tool={},
                trace=Mock(),
                stop=Mock(),
                tool=Mock(return_value=({"output": "ok"}, None)),
                tool_completed=Mock(),
                manifest={"effective_settings": {"native_workstation_permissions": inputs.WORKSTATION_PERMISSIONS}},
                visible={"tools": [], "prompts": {"one": ("task",)}},
            )

            from swarmform.__main__ import Cohort
            cohort.deadline = None
            cohort.active = Cohort.active.__get__(cohort)
            cohort.remaining = Cohort.remaining.__get__(cohort)
            cohort.run_tool = Cohort.run_tool.__get__(cohort)
            cohort.prompts = Cohort.prompts.__get__(cohort)
            cohort.tool_reply = Cohort.tool_reply.__get__(cohort)
            cohort.stopper = Mock()
            cohort.stopper.stop_actor.return_value = {"research_stop_verified": True}
            cohort.continue_research = Cohort.continue_research.__get__(cohort)
            agent.prompt.side_effect = lambda text: (cohort.stopping.set()
                if text.startswith("Progress report recorded.") else None)

            def create(kind, actor, events, **kwargs):
                self.assertEqual(kwargs["workstation_permissions"], inputs.WORKSTATION_PERMISSIONS)
                call = {
                    "type": "function_call",
                    "name": "bash",
                    "call_id": "c1",
                    "arguments": json.dumps({"command": "pwd"}),
                }
                kwargs["on_transport_response"](
                    {"model": "openai/gpt-6.1-sol", "usage": {"total_tokens": 15}}
                )
                for message in [
                    {"type": "ready", "cwd": directory},
                    {"type": "response_update", "response": {"output": [call]}},
                    {"type": "tool_call", "id": "reply", "call_id": "c1|tool"},
                    {
                        "type": "provider_response",
                        "event": {
                            "response": {
                                "output": [call],
                                "usage": {"total_tokens": 15},
                            }
                        },
                    },
                    {"type": "settled", "text": "done"},
                ]:
                    events.put((actor, message))
                return agent

            with patch(
                "swarmform.native_participant.model_session.create", side_effect=create
            ):
                cohort.stopping.clear()
                await participate(cohort, "one")
            self.assertEqual(cohort.errors, {})
            self.assertEqual(
                cohort.usage["one"], {"responses": 1, "tools": 1, "tokens": 15}
            )
            cohort.tool.assert_called_once_with("one", "pwd", "c1", None)
            agent.reply.assert_called_once()
            agent.close.assert_called_once()
            self.assertEqual(cohort.returns, {})
            self.assertIn('"tokens": 999985', agent.prompt.call_args.args[0])

            # Closing the native session is part of successful evidence capture.
            agent.close.side_effect = OSError("native transcript not saved")
            cohort.errors.clear()
            cohort.stop.reset_mock()
            with patch(
                "swarmform.native_participant.model_session.create", side_effect=create
            ):
                cohort.stopping.clear()
                await participate(cohort, "one")
            self.assertIn("native transcript not saved", cohort.errors["close_one"])
            cohort.stop.assert_called_with("participant_cleanup_error")

            # Missing usage must not be counted as free work under a matched budget.
            agent.close.side_effect = None
            cohort.errors.clear()
            cohort.stop.reset_mock()

            def missing_usage(kind, actor, events, **kwargs):
                kwargs["on_transport_response"]({"model": "fixture", "usage": {}})
                events.put((actor, {"type": "settled", "text": "done"}))
                return agent

            with patch(
                "swarmform.native_participant.model_session.create",
                side_effect=missing_usage,
            ):
                cohort.stopping.clear()
                await participate(cohort, "one")
            self.assertIn("positive token usage", cohort.errors["one"])
            cohort.stop.assert_called_with("participant_error")

if __name__ == "__main__":
    unittest.main()
