#!/usr/bin/env python3
"""Offline controller checks using synthetic responses, never a model endpoint."""
import argparse
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch

import run
import review


class Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def verify(root):
    checks = {}
    old = run.REPO / "experiments/wayfinding-live-peers"
    assert (run.ROOT / "scenario.py").read_bytes() == (old / "scenario.py").read_bytes()
    checks["subject_scenario_identical_to_current_pilot"] = True
    archived = old / "results/2026-10-17"
    old_tasks = review.read(archived / "tasks.json")
    for actor, task in run.TASKS.items():
        expected = old_tasks[actor].replace(" Keep the source workbook unchanged. Finish closes the entire assignment.", "")
        assert task == expected
    old_tools = review.read(archived / "tools.json")
    assert len(run.TOOLS) == len(old_tools)
    for tool, old_tool in zip(run.TOOLS, old_tools):
        assert {k:v for k,v in tool.items() if k!='description'} == {k:v for k,v in old_tool.items() if k!='description'}
    assert run.base.INSTRUCTIONS == review.read(archived / "registration.json")["instructions"]
    checks["business_work_and_tool_schemas_preserved"] = True
    assert (run.MAX_RESPONSES, run.MAX_TOOLS, run.MAX_WORLD, run.MAX_BATCH) == (512, 1024, 21600, 86400)
    assert run.MAX_BATCH >= 2 * run.MAX_WORLD
    assert (run.REQUEST_TIMEOUT, run.MAX_WAIT) == (150, 30)
    checks["larger_limits_and_two_full_worlds_fit"] = True

    # Block network access as well as replacing the provider function.
    with patch("urllib.request.urlopen", side_effect=AssertionError("Offline checks must not access the network")):
        with redirect_stdout(io.StringIO()):
            run.prepare(root)
        reg = run.frozen(root)
        assert reg["budget_profile"] == "live-peers-extended-v1"
        assert all(reg[k] == v for k, v in run.BUDGETS.items() if k != "profile")
        checks["registration_and_code_freeze_include_budget_profile"] = True
        assert review.read(root / "qualification.json")["passed"]
        checks["all_existing_deterministic_controls_pass"] = True

        registration_path = root / "registration.json"
        original_bytes = registration_path.read_bytes()
        wrong = deepcopy(reg)
        wrong["max_responses_per_actor"] = 32
        run.save(registration_path, wrong)
        try:
            try:
                run.frozen(root)
            except AssertionError:
                checks["mismatched_registered_budget_rejected"] = True
            else:
                raise AssertionError("A stale budget was admitted")
        finally:
            registration_path.write_bytes(original_bytes)

        refs = review.verify_references(root)
        cases = []

        def case(name, finish_at=None, waits=0, jump_after_first=0, tool_cap=None):
            clock = Clock()
            calls = []

            def provider(body, trace, label, timeout):
                n = len(calls) + 1
                operation = "finish" if finish_at == n else "wait_for_update" if n <= waits else "cache_list"
                arguments = {"text": "Synthetic offline controller check"} if operation == "finish" else {}
                request = {"model": run.base.MODEL, "store": False, "stream": True,
                           "parallel_tool_calls": False, **deepcopy(body)}
                response = {"model": run.base.MODEL, "reasoning": {"effort": run.base.EFFORT},
                            "status": "completed", "output": [{"type": "function_call", "name": operation,
                            "arguments": json.dumps(arguments), "call_id": f"offline-{name}-{n}"}]}
                run.save(trace / f"{label}.request.json", request)
                run.save(trace / f"{label}.response.json", response)
                assert 0 < timeout <= 150
                calls.append(operation)
                if n == 1:
                    clock.now += jump_after_first
                return response

            cell = {"id": name, "split": True, "actor_order": ["alpha"]}
            with ExitStack() as stack:
                stack.enter_context(patch.object(run.base, "call", provider))
                stack.enter_context(patch.object(run.time, "monotonic", clock.monotonic))
                stack.enter_context(patch.object(run.time, "sleep", clock.sleep))
                if tool_cap is not None:
                    stack.enter_context(patch.object(run, "MAX_TOOLS", tool_cap))
                with redirect_stdout(io.StringIO()):
                    run.run_world(root, cell)
            result = review.read(root / name / "alpha/result.json")
            audited = review.audit_world(root, cell, reg, refs)
            assert audited["exact_actor_histories_and_global_states_replayed"]
            assert result["steps"] == len(calls) == result["tools"]
            scheduler = review.read(root / name / "scheduler.json")
            row = {"case": name, "synthetic_responses": len(calls), "status": result["status"],
                   "limit_reached": result.get("limit_reached"), "limit_value": result.get("limit_value"),
                   "wait_returns": sum(e["event"] == "wait_return" for e in scheduler),
                   "exact_history_and_state_replay": True}
            cases.append(row)
            return row

        row = case("offline-completes-after-100", finish_at=101)
        assert row["synthetic_responses"] == 101 and row["status"] == "completed"
        checks["past_32_and_100_calls_without_early_stop"] = True

        row = case("offline-response-cap")
        assert row["synthetic_responses"] == 512 and row["status"] == "budget_exhausted"
        assert row["limit_reached"] == "max_responses_per_actor" and row["limit_value"] == 512
        checks["512_response_limit_enforced_and_identified"] = True

        row = case("offline-past-old-time-cap", finish_at=2, jump_after_first=601)
        assert row["synthetic_responses"] == 2 and row["status"] == "completed"
        checks["old_600_second_cap_does_not_truncate_new_world"] = True

        row = case("offline-world-cap", jump_after_first=21600)
        assert row["synthetic_responses"] == 1 and row["status"] == "world_timeout"
        assert row["limit_reached"] == "max_world_seconds" and row["limit_value"] == 21600
        checks["six_hour_world_cap_enforced_and_identified"] = True

        row = case("offline-tool-cap-override", tool_cap=3)
        assert row["synthetic_responses"] == 3 and row["status"] == "budget_exhausted"
        assert row["limit_reached"] == "max_tools_per_actor" and row["limit_value"] == 3
        checks["separate_tool_guard_enforced_with_test_only_override"] = True

        row = case("offline-wait-accounting", finish_at=3, waits=2)
        assert row["synthetic_responses"] == 3 and row["wait_returns"] == 2 and row["status"] == "completed"
        checks["local_waits_make_no_extra_provider_calls"] = True

    # Validate the complete earlier archive without rewriting it.
    manifest = review.read(archived / "artifact-manifest.json")
    hashes = manifest["files"]
    for name, expected in hashes.items():
        assert hashlib.sha256((archived / name).read_bytes()).hexdigest() == expected
    checks["previous_archive_byte_integrity"] = True
    result = {"checked_at": datetime.now(timezone.utc).isoformat(), "passed": all(checks.values()),
              "scope": "Offline synthetic controller checks, not model behavior or current model access verification",
              "real_model_requests": 0, "network_access_blocked": True, "budget_profile": run.BUDGETS,
              "checks": checks, "synthetic_cases": cases, "previous_archive_files_verified": len(hashes)}
    run.save(root / "offline-verification.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    verify(parser.parse_args().output)
