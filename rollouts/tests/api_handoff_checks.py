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
    def test_external_review_view_is_bounded_without_pruning_local_rows(self):
        from swarmform.checkpoint import (
            MAX_REVIEW_REQUEST_BYTES,
            bounded_review_rows,
            review_request,
        )

        rows = [
            {
                "id": i,
                "actor": f"Research{i % 8 + 1:02d}",
                "command": "x" * 20_000,
                "stdout": "y" * 20_000,
                "success": True,
            }
            for i in range(800)
        ]
        view, size, truncated = bounded_review_rows(rows)
        self.assertTrue(truncated)
        self.assertLessEqual(size, MAX_REVIEW_REQUEST_BYTES)
        self.assertLess(len(view), len(rows))
        self.assertEqual(len(rows[0]["command"]), 20_000)
        args = SimpleNamespace(
            model="fixture",
            served_model=None,
            review_model=None,
            api_protocol="chat-completions",
        )
        payload = review_request(args, view)[1]
        self.assertLessEqual(
            len(json.dumps(payload, ensure_ascii=False).encode()),
            MAX_REVIEW_REQUEST_BYTES,
        )

    def test_provider_context_is_bounded_without_pruning_local_history(self):
        from swarmform.__main__ import API_CONTEXT_BYTES, provider_messages

        messages = [
            {"role": "tool", "tool_call_id": str(i),
             "content": json.dumps({"stdout": "z" * 12_000, "exit_code": 0})}
            for i in range(80)
        ]
        projected = provider_messages(messages)
        self.assertLessEqual(len(json.dumps(projected).encode()), API_CONTEXT_BYTES)
        self.assertEqual(len(messages), 80)
        self.assertEqual(len(json.loads(messages[0]["content"])["stdout"]), 12_000)

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
        task_count = len({row["task"] for row in rows})
        self.assertEqual(len(rows), task_count * len(CHANNELS) * 4)
        self.assertEqual(
            list(dict.fromkeys(r["population"] for r in rows)), [4, 8, 16, 32]
        )
        self.assertEqual(
            sum(row["population"] for row in rows),
            task_count * len(CHANNELS) * sum((4, 8, 16, 32)),
        )

    def test_finished_or_archived_attempts_are_not_restarted(self):
        import hashlib

        args = ["--tasks", "planning-possible", "--populations", "4"]
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

        family_assets = {}
        for task in inputs.TASK_MODULES:
            direct, _, _ = inputs.build_intended(task, 3)
            family = task.split("-")[0]
            self.assertEqual(family_assets.setdefault(family, direct["project_artifacts"]), direct["project_artifacts"])
            for channel in inputs.CHANNELS:
                incidental, _, _ = inputs.build(task, channel, 3)
                self.assertEqual(direct["project_artifacts"], incidental["project_artifacts"])
                for actor, (system, instruction) in incidental["prompts"].items():
                    title = incidental["startup"][actor]["/workspace/task.md"].splitlines()[0]
                    self.assertEqual(instruction, f"Complete the task in /workspace/task.md ({title}).")
                    self.assertEqual(direct["prompts"][actor], [
                        system, "You are one of 3 participants working together on this task. " + instruction,
                    ])
                    self.assertNotIn("/workspace/interfaces.txt", incidental["startup"][actor])
                    for material in (incidental, direct):
                        self.assertNotIn("/workspace/research-session.md", material["startup"][actor])
        for cue, intended in [
            ("Share your source files.", True), ("Read work-queue.md.", True),
            ("Assign subtasks.", False), ("Use [HANDOFF].", True), ("Other agents are present.", False),
        ]:
            material = deepcopy(direct if intended else incidental)
            actor_files = next(iter(material["startup"].values()))
            actor_files["/workspace/manual.txt"] = cue
            self.assertFalse(audit_visible(material, intended=intended)["passed"], cue)

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
                ),
                out=Path(directory),
                stopping=threading.Event(),
                usage={},
                errors={},
                returns={},
                active_tools=set(),
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
                    {"type": "ready"},
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
            cohort.tool.assert_called_once_with("one", "pwd", "c1")
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
