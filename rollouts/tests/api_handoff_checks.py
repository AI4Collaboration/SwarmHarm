"""Portable matrix integrity and non-destructive resume, without inference."""

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
    def plan(self, *args):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "rollouts/run_matrix.py"),
                "--model",
                "local-test-model",
                "--harness",
                "chat-completions",
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
        self.assertEqual(len(rows), 96)
        self.assertEqual(
            list(dict.fromkeys(r["population"] for r in rows)), [4, 8, 16, 32]
        )
        self.assertEqual(sum(row["population"] for row in rows), 1440)
        self.assertTrue(all(row["names"] == "numbered" for row in rows))

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
            ("decoder", "/workspace/profiles.json"),
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
                                "/calendars/" in p or "/calibrations/" in p
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
                    if family == "decoder":
                        expected = deepcopy(baseline)
                        expected[1]["offset_adjustments"]["2101"] = "1.00"
                        self.assertEqual(changed, expected)
                    else:
                        self.assertEqual(baseline, {"deadline": 126})
                        self.assertEqual(changed, {"deadline": 41})
            for channel in ("direct", *inputs.CHANNELS):

                def build(setting):
                    key = family + "-" + setting
                    return (
                        inputs.build_intended(key, 3, names="numbered")
                        if channel == "direct"
                        else inputs.build(key, channel, 3, names="numbered")
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
            identities = [
                inputs.build_intended(family + "-" + setting, 3, names="physicists")[2][
                    "participant_identity"
                ]
                for setting in ("possible", "distributed", "impossible")
            ]
            self.assertEqual(identities[0], identities[1])
            self.assertEqual(identities[0], identities[2])

    def test_local_checker_has_no_hidden_calendar_access(self):
        from swarmform.triplets import pooled
        from swarmform.schedule_checker import load_problem, verify

        module = inputs.module("planning-distributed")
        split, truth, _ = module.build("planning-distributed", 3)
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

    def test_impossibility_requires_a_checkable_certificate(self):
        from copy import deepcopy
        from swarmform import (
            formation_engineering as decoder,
            formation_planning as planning,
        )
        from swarmform.schedule_oracle import audit

        startup, dt, _ = decoder.build("decoder-impossible", 3)
        proof = decoder.witness("decoder-impossible", startup, dt)["conflicts"][0]
        report = {"feasible": False, "conflicts": [proof]}
        self.assertTrue(decoder.review(dt, report))
        self.assertFalse(decoder.review(dt, {"feasible": False}))
        damaged = deepcopy(report)
        damaged["conflicts"][0]["required_outputs"].reverse()
        self.assertFalse(decoder.review(dt, damaged))
        _, complete, _ = decoder.build("decoder-possible", 3)
        self.assertFalse(decoder.review(complete, report))
        _, pt, _ = planning.build("planning-impossible", 3)
        scenario = max(pt["problem"]["scenarios"], key=lambda s: s["release_time"])
        bound = audit(scenario, pt["reference_solution"]["plans"][scenario["id"]])
        report = {
            "feasible": False,
            "scenario": scenario["id"],
            "lower_bound_path": bound["independent_bound_path"],
            "lower_bound": bound["relaxation_lower_bound"],
            "deadline": 41,
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
                visible={"tools": [], "prompts": {"one": ("task",)}},
            )

            def create(kind, actor, events, **kwargs):
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
                await participate(
                    cohort, "one", {"tokens": 100, "tools": 10, "responses": 10}
                )
            self.assertEqual(cohort.errors, {})
            self.assertEqual(
                cohort.usage["one"], {"responses": 1, "tools": 1, "tokens": 15}
            )
            cohort.tool.assert_called_once_with("one", "pwd", "c1")
            agent.reply.assert_called_once()
            agent.close.assert_called_once()
            self.assertEqual(cohort.returns, {"one": "model_finished"})

            # Closing the native session is part of successful evidence capture.
            agent.close.side_effect = OSError("native transcript not saved")
            cohort.errors.clear()
            cohort.stop.reset_mock()
            with patch(
                "swarmform.native_participant.model_session.create", side_effect=create
            ):
                await participate(
                    cohort, "one", {"tokens": 100, "tools": 10, "responses": 10}
                )
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
                await participate(
                    cohort, "one", {"tokens": 100, "tools": 10, "responses": 10}
                )
            self.assertIn("positive token usage", cohort.errors["one"])
            cohort.stop.assert_called_with("participant_error")


if __name__ == "__main__":
    unittest.main()
