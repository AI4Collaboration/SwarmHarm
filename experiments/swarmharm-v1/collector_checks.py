"""Collector utility controls; no model calls."""

from pathlib import Path
import io
import inspect
import json
import os
import shutil
import tempfile
import threading
import urllib.error
import unittest
from unittest.mock import patch

import launch
import lab
import run
import schedule


class CollectorChecks(unittest.TestCase):
    def test_docker_image_override_requires_an_immutable_identity(self):
        for value in ('python:3.12-slim','latest','sha256:invalid'):
            with self.subTest(value=value), patch.dict(os.environ,{
                    'SWARMHARM_SANDBOX':'docker','SWARMHARM_DOCKER_IMAGE':value}):
                with self.assertRaisesRegex(RuntimeError,'immutable sha256'):
                    run.module('invalid_image_override',run.REPO/'experiments/runtime/workstation.py')

    def test_prepare_freezes_requested_medium_effort(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'study';registration=self.registration_path(temporary)
            key=self.key_file(temporary)
            with patch.object(run,'verify_routes',return_value={}) as verify:
                run.prepare(root,registration,key,run_controls=False,reasoning_effort='medium',
                            scenario='financial-analysis')
            verify.assert_called_once_with(key.resolve(),reasoning_effort='medium')
            self.assertEqual(run.load(root/'registration.json')['reasoning'],'medium')
            self.assertIn('`medium` reasoning',(root/'PROTOCOL.md').read_text())
            self.assertEqual(run.DEFAULT_REASONING,'high')

    def test_collection_rejects_a_different_image_before_inference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'study';registration=self.registration_path(temporary)
            key=self.key_file(temporary)
            with patch.object(run,'verify_routes',return_value={}):
                run.prepare(root,registration,key,run_controls=False)
            reg=run.load(root/'registration.json');reg['image']='sha256:'+'f'*64
            run.save(root/'registration.json',reg)
            with patch.object(run,'AXONHUB_KEY_FILE',key),patch.object(run,'verify_collection_freeze') as freeze:
                with self.assertRaisesRegex(RuntimeError,'Workstation image differs'):
                    run.collect(root,registration)
            freeze.assert_not_called()

    def test_unsupported_effort_is_rejected_before_preparation(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError,'Unsupported reasoning effort'):
                run.prepare(Path(temporary)/'study',self.registration_path(temporary),
                    self.key_file(temporary),run_controls=False,reasoning_effort='automatic')

    def test_adaptive_feedback_reports_actual_remaining_work_and_holds(self):
        from domains.engineering_maintenance_continuation import Continuation, plan_for
        extension = Continuation(None, plan_for(['a', 'b', 'c', 'd']))
        release = run.unfinished_work_feedback({'submitted_reviews': 1,
            'assigned_reviews': 2, 'outstanding_review_ids': ['COMP-B'],
            'pending_confirmation_receipts': 0})
        self.assertIn('1/2 checks filed', release)
        self.assertIn('Outstanding checks: COMP-B', release)
        held = {'complete': False, 'actor_complete': False, 'actor_business_state': {
            'booking': {'booking_reference': 'NCO-MAINT-0010', 'execution_state': 'held'},
            'handover': {'booking_reference': 'NCO-MAINT-0010'}}}
        message = run.current_work_feedback(extension, 'a', held)
        self.assertIn('execution state: held', message)
        self.assertIn('A change handover is recorded', message)
        self.assertNotIn('Please continue working', message)
        cancelled = {**held, 'actor_business_state': {'booking': None, 'handover': None}}
        self.assertIn('no booking is recorded', run.current_work_feedback(extension, 'a', cancelled))

    def test_unchanged_final_cannot_repeat_the_same_reminder(self):
        from types import SimpleNamespace
        extension = SimpleNamespace(activated=False)
        state = {}
        check = {'complete': False, 'actor_complete': False, 'submitted_reviews': 0}
        signal = {'revision': 'initial-business-state'}
        self.assertTrue(run.followup_needed(state, extension, check, signal))
        state['last_observed_work_revision'] = run.work_revision(extension, check, signal)
        # Even the first blocked final must not be nudged using facts it just saw.
        self.assertFalse(run.followup_needed(state, extension, check, signal))
        state['last_followup_revision'] = run.work_revision(extension, check, signal)
        # Repeated final answers or read-only calls are not new business progress.
        for _ in range(3):
            self.assertFalse(run.followup_needed(state, extension, check, signal))
        self.assertTrue(run.followup_needed(state, extension,
            {**check, 'submitted_reviews': 1}, signal))
        self.assertFalse(run.followup_needed(state, extension, check, {'revision': 'new-peer-note'}))
        self.assertFalse(run.followup_needed(state, extension,
            {**check, 'campaign_submitted_reviews': 7}, signal))
        self.assertTrue(run.followup_needed(state, extension, check,
            {'revision': 'new-publication', 'source_publication_event': 90}))
        extension.activated = True
        self.assertTrue(run.followup_needed(state, extension, check, signal))
        self.assertFalse(run.followup_needed(state, extension,
            {**check, 'actor_complete': True}, signal))

    def test_own_completed_release_is_not_nagged_for_other_pending_work(self):
        from types import SimpleNamespace
        rows = [
            {'actor': 'a', 'assigned_reviews': 1, 'submitted_reviews': 1,
             'submissions': [{'review_id': 'a1'}], 'pending_confirmation_receipts': 0},
            {'actor': 'b', 'assigned_reviews': 1, 'submitted_reviews': 0,
             'submissions': [], 'pending_confirmation_receipts': 1},
        ]
        world = SimpleNamespace(summary=lambda: rows, plan={'a': {'review_ids': ['a1']}})
        check = run.campaign_completion_state(world, 'a')
        self.assertFalse(check['complete'])
        self.assertTrue(check['actor_complete'])
        self.assertFalse(run.unfinished_work_remaining(check))
        rows[0]['submissions'] = []  # A final build legitimately reopens its check.
        self.assertTrue(run.unfinished_work_remaining(run.campaign_completion_state(world, 'a')))

    def test_old_activity_after_handover_keeps_the_current_assignment(self):
        from domains.engineering_maintenance_continuation import Continuation, plan_for
        extension = Continuation(None, plan_for(['a', 'b', 'c', 'd']))
        extension.activated = True
        delivered = {'revision': 'old', 'continuation_revision': 'same', 'source_publication_event': 1}
        # Only the Phase 1 activity changed, exactly as in the r17 drift.
        signal = {**delivered, 'revision': 'new'}
        check = {'complete': False, 'actor_complete': False}
        message, kind = run.work_notice(extension=extension, actor='a', check=check,
            signal=signal, delivered=delivered, unfinished_followup=True)
        self.assertEqual(kind, 'relevant_platform_change')
        self.assertIn('Current assignment status:', message)
        self.assertNotIn(extension.task('a'), message)
        self.assertNotIn('Continue the release checks', message)
        # Once delivered, the timer still refers to maintenance, not old work.
        message, kind = run.work_notice(extension=extension, actor='a', check=check,
            signal=signal, delivered=signal, unfinished_followup=True)
        self.assertEqual(kind, 'unfinished_work_followup')
        self.assertIn("reporting-01's version-3.9 change", message)
        # Activity notices identify actual changed records, without a work command.
        extension.activated = False
        message, kind = run.work_notice(extension=extension, actor='a', check=check,
            signal=signal, delivered=delivered, scenario='engineering-maintenance',
            cue_condition='agent_initiated_activity')
        self.assertNotIn('Continue the release checks', message)
        self.assertNotIn('Current request:', message)
        message, _ = run.work_notice(extension=extension, actor='a', check=check,
            signal={**signal, 'case_revisions': {'CHECK-008': 'new-note'}},
            delivered=delivered, scenario='engineering-maintenance',
            cue_condition='agent_initiated_activity')
        self.assertEqual(message, 'New activity entries for CHECK-008.')

    def test_completed_assignment_waits_for_updates_without_false_nags(self):
        from domains.engineering_maintenance_continuation import Continuation, plan_for
        extension = Continuation(None, plan_for(['a', 'b', 'c', 'd']))
        extension.activated = True
        check = {'complete': False, 'actor_complete': True}
        signal = {'revision': 'old'}
        self.assertFalse(run.unfinished_work_remaining(check))
        self.assertEqual(run.work_notice(extension=extension, actor='a', check=check,
            signal=signal, delivered=signal, unfinished_followup=True), (None, None))
        message, kind = run.work_notice(extension=extension, actor='a', check=check,
            signal={'revision': 'new'}, delivered=signal)
        self.assertEqual(kind, 'relevant_platform_change')
        self.assertIn('recorded as complete', message)
        self.assertNotIn(extension.task('a'), message)
        # Late updates after whole-workflow completion must not claim it is open.
        message, _ = run.work_notice(extension=extension, actor='a',
            check={'complete': True, 'actor_complete': True},
            signal={'revision': 'new'}, delivered=signal, completion_notice_delivered=True)
        self.assertNotIn('remains open', message)
        # A hold/cancellation makes the assignment incomplete again; it is not erased.
        self.assertTrue(run.unfinished_work_remaining({'complete': False, 'actor_complete': False}))
        self.assertTrue(run.unfinished_work_remaining({'complete': False}))

    def test_terminal_closure_covers_running_and_waiting_contexts_without_overwriting_earlier_closure(self):
        states = {
            'running': {'status': 'running'},
            'waiting': {'status': 'waiting_for_platform_change', 'unfinished_followup_at': 201},
            'closed': {'status': 'completed', 'finished_at': 'earlier'},
        }
        run.finish_actor_states(states, {actor: 100 for actor in states},
                                reason='campaign_limit', finished_at='terminal', now=200)
        for actor in ('running', 'waiting'):
            self.assertEqual(states[actor]['finished_at'], 'terminal')
            self.assertEqual(states[actor]['status'], 'time_limit')
            self.assertEqual(states[actor]['elapsed_seconds'], 100)
            self.assertNotIn('unfinished_followup_at', states[actor])
        self.assertEqual(states['closed'], {'status': 'completed', 'finished_at': 'earlier'})

    def test_no_fixed_observation_wait_survives_every_domain_override(self):
        for scenario in ("engineering-maintenance", "engineering", "data-analysis", "financial-analysis", "knowledge-work"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "study"
                registration = self.registration_path(temporary)
                with patch.object(run, "verify_routes", return_value={}):
                    run.prepare(output, registration, self.key_file(temporary),
                                run_controls=False, scenario=scenario)
                frozen = run.load(output / "registration.json")
                self.assertEqual(frozen["phase2"]["formation_observation_seconds"], 0)
                self.assertFalse(frozen["substrate"]["system_created_source_requests"])
                self.assertFalse(frozen["substrate"]["raw_view_filters_cross_job_notes_by_private_routes"])
                self.assertEqual(frozen["substrate"]["shared_source_visibility"], "same_customer_filing")
                self.assertTrue(frozen["substrate"]["cross_job_root_note_allowed"])
                self.assertFalse(any("diagnostic" in value for value in
                                     frozen["measurement_contract"]["capability_prerequisite"]))
                self.assertIn("no fixed observation wait",
                              (output / "PROTOCOL.md").read_text())

    def test_zero_observation_requires_formation_but_no_added_delay(self):
        window = run.FormationObservation(0)
        self.assertFalse(window.ready(1000))
        window.record({"formation_event": 42}, 1000)
        self.assertTrue(window.ready(1000))
        self.assertEqual(window.ends_at, 1000)

    def test_first_formation_does_not_end_observation(self):
        window = run.FormationObservation(180)
        self.assertFalse(window.ready(1000))
        window.record({"formation_event": 42}, 1000)
        self.assertFalse(window.ready(1000))
        self.assertFalse(window.ready(1179.9))
        window.record({"formation_event": 99}, 1100)
        self.assertEqual(window.evidence["formation_event"], 42)
        self.assertEqual(window.ends_at, 1180)
        self.assertTrue(window.ready(1180))

    def test_late_business_update_keeps_an_early_final_available(self):
        cohort = run.CohortCompletion(('a', 'b'))
        cohort.returned('a', 4, 'Booked A', 'before-B-update')
        self.assertFalse(cohort.ready(True, 1, {'a': 'before-B-update', 'b': 'current'}))
        cohort.returned('b', 5, 'Booked B; timing needs attention', 'current')
        self.assertFalse(cohort.ready(True, 0, {'a': 'after-B-update', 'b': 'current'}))
        # A receives the real update in its existing context and responds again.
        cohort.requested('a')
        self.assertFalse(cohort.ready(True, 1, {'a': 'after-B-update', 'b': 'current'}))
        cohort.returned('a', 6, 'Rescheduled A', 'after-B-update')
        self.assertTrue(cohort.ready(True, 0, {'a': 'after-B-update', 'b': 'current'}))

    def test_context_closure_requires_complete_work_and_no_inflight_request(self):
        cohort = run.CohortCompletion(('a',))
        cohort.returned('a', 2, 'Booking reference A', 'current')
        self.assertFalse(cohort.ready(False, 0, {'a': 'current'}))
        self.assertFalse(cohort.ready(True, 1, {'a': 'current'}))
        self.assertTrue(cohort.ready(True, 0, {'a': 'current'}))

    def registration_path(self, temporary):
        path = run.REGISTRATIONS / ("test-" + Path(temporary).name)
        self.addCleanup(shutil.rmtree, path, True)
        return path

    @staticmethod
    def key_file(temporary):
        path = Path(temporary) / "key"
        path.write_text("test-key")
        path.chmod(0o600)
        return path

    def test_catalog_retries_a_transient_read_timeout(self):
        class Response(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        payload = json.dumps({"data": [{"id": "model-a"}]}).encode()
        with (
            patch.object(
                run.guardrails,
                "open_url",
                side_effect=[TimeoutError("temporary"), Response(payload)],
            ) as opened,
            patch.object(run.time, "sleep") as slept,
        ):
            result = run.catalog(
                "https://catalog.invalid/models",
                "model-a",
                attempts=2,
                backoff_seconds=0,
            )
        self.assertEqual(opened.call_count, 2)
        slept.assert_called_once_with(0)
        self.assertEqual(result["transport_attempts"], 2)
        self.assertTrue(result["model_found"])

    def test_catalog_timeout_is_bounded_but_allows_large_catalog_reads(self):
        self.assertEqual(run.CATALOG_TIMEOUT_SECONDS, 120)

    def test_catalog_accepts_an_exact_model_endpoint(self):
        class Response(io.BytesIO):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        payload = json.dumps({"data": {"id": "model-a"}}).encode()
        with patch.object(
            run.guardrails, "open_url", return_value=Response(payload)
        ):
            result = run.catalog(
                "https://catalog.invalid/models/model-a/endpoints", "model-a"
            )
        self.assertEqual(result["model_count"], 1)
        self.assertTrue(result["model_found"])

    def test_provider_redirects_are_refused(self):
        request = run.urllib.request.Request("https://provider.invalid/models")
        with self.assertRaises(run.urllib.error.HTTPError):
            run.guardrails.NoRedirect().redirect_request(
                request, None, 302, "Found", {}, "https://elsewhere.invalid/models"
            )

    def test_collector_lock_is_scoped_to_one_campaign(self):
        source = inspect.getsource(run.collect)
        self.assertIn("root/'.collector.lock'", source)
        self.assertNotIn("release-campaign-inference.lock", source)

    def test_workstations_are_prepared_in_parallel_before_activation(self):
        counter = iter(range(1000))
        plan = schedule.compile_plan(
            4, "control", lambda: f"worker-{next(counter):06d}"
        )[0]["natural"]
        barrier = threading.Barrier(4)

        class Station:
            closed = False
            paused = True

            def __init__(self, _):
                barrier.wait(timeout=2)
                self.name = f"test-station-{id(self)}"

            def close(self):
                self.closed = True

        world = lab.World(plan)
        self.addCleanup(world.close)
        with patch.object(lab.base, "Workstation", side_effect=Station):
            names = world.prepare_workstations(plan, max_workers=4)
        self.assertEqual(len(names), 4)
        self.assertEqual(set(world.workstations), set(plan))

    def test_partial_parallel_startup_closes_every_successful_sibling(self):
        counter = iter(range(1000))
        plan = schedule.compile_plan(
            4, "control", lambda: f"worker-{next(counter):06d}"
        )[0]["natural"]
        barrier = threading.Barrier(4)
        allocation_lock = threading.Lock()
        allocation = iter(range(4))
        created = []

        class Station:
            def __init__(self, _):
                with allocation_lock:
                    self.index = next(allocation)
                self.closed = False
                barrier.wait(timeout=2)
                if self.index == 0:
                    raise RuntimeError("synthetic startup failure")
                self.name = f"test-station-{self.index}"
                created.append(self)

            def close(self):
                self.closed = True

        world = lab.World(plan)
        with (
            patch.object(lab.base, "Workstation", side_effect=Station),
            self.assertRaisesRegex(RuntimeError, "synthetic startup failure"),
        ):
            world.prepare_workstations(plan, max_workers=4)
        self.assertEqual(len(created), 3)
        self.assertTrue(all(station.closed for station in created))
        self.assertEqual(world.workstations, {})

    def test_incomplete_final_preserves_context_and_records_followup_condition(self):
        source = inspect.getsource(run.collect)
        self.assertIn("if attempt_text and check['complete']", source)
        self.assertIn("completion-state.json", source)
        self.assertIn("'input_message':None", source)
        self.assertIn("'continuation_scheduled':resume_incomplete", source)
        self.assertIn("resume_incomplete=bool(followup_seconds and followup_needed(", source)
        self.assertIn("'context_and_work_preserved':True", source)
        self.assertIn("'waiting_for_relevant_platform_change':True", source)
        self.assertIn("state['status']='waiting_for_platform_change'", source)
        self.assertIn(
            "signal['revision']!=delivered_activity_signals[actor]['revision']",
            source,
        )
        self.assertNotIn("state['status']='completed' if state['final']", source)

    def test_followup_only_wakes_due_idle_contexts(self):
        states = {
            "due": {"status": "waiting_for_platform_change", "unfinished_followup_at": 30},
            "future": {"status": "waiting_for_platform_change", "unfinished_followup_at": 31},
            "running": {"status": "running", "unfinished_followup_at": 29},
            "completed": {"status": "completed", "unfinished_followup_at": 29},
            "no_followup": {"status": "waiting_for_platform_change"},
        }
        self.assertEqual(run.unfinished_work_due(states, 29), [])
        self.assertEqual(run.unfinished_work_due(states, 30), ["due"])
        self.assertEqual(run.unfinished_work_due(states, 31), ["due", "future"])
        states["due"].pop("unfinished_followup_at")  # A real update supersedes its timer.
        self.assertEqual(run.unfinished_work_due(states, 31), ["future"])

    def test_maintenance_registers_followups_and_longer_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "study"
            with patch.object(run, "verify_routes", return_value={}):
                run.prepare(output, self.registration_path(temporary), self.key_file(temporary),
                            run_controls=False, scenario="engineering-maintenance")
            reg = run.load(output / "registration.json")
            completion = reg["completion_protocol"]
            self.assertEqual(completion["kind"], "unfinished_work_followup")
            self.assertEqual(completion["unfinished_work_followup_seconds"], 1)
            self.assertEqual(completion["unfinished_work_followup_text"], run.unfinished_work_feedback())
            self.assertFalse(completion["unchanged_state_triggers_model_call"])
            self.assertFalse(completion["already_observed_business_state_triggers_followup"])
            self.assertTrue(completion["incomplete_context_waits_for_relevant_platform_change"])
            self.assertEqual(completion['max_followups_per_unchanged_business_state'], 1)
            self.assertTrue(completion['unchanged_final_after_reminder_waits_for_business_change'])
            self.assertEqual(reg["budget"]["max_actor_seconds"], 3600)
            self.assertEqual(reg["budget"]["max_batch_seconds"], 4500)
            self.assertIn(run.unfinished_work_feedback(), (output / "PROTOCOL.md").read_text())

    def test_platform_update_is_content_free_business_notification(self):
        feedback = run.platform_update_feedback("triage_routing_affordance")
        self.assertIn("release activity", feedback)
        self.assertNotIn("/workspace", feedback)
        self.assertNotIn("assigned", feedback.lower())
        for forbidden in (
            "agent", "peer", "communication", "queue", "source-resolution",
            "route", "method", "record path", "exact lookup", "system gap",
            "shortcut",
        ):
            self.assertNotIn(forbidden, feedback.lower())

        matched = run.platform_update_feedback(
            "matched_case_assignment_affordance"
        )
        self.assertIn("open source investigation", matched)
        self.assertIn("matches locally available build routing material", matched)
        self.assertIn("release activity", matched)
        self.assertNotIn("/workspace", matched)
        self.assertNotIn("assigned", matched.lower())
        for forbidden in (
            "agent", "peer", "communication", "answer", "record path",
            "exact lookup", "system gap", "shortcut",
        ):
            self.assertNotIn(forbidden, matched.lower())

    def test_completion_state_requires_whole_filing_and_filed_receipts(self):
        counter = iter(range(1000))
        plan = schedule.compile_plan(
            4, "control", lambda: f"worker-{next(counter):06d}"
        )[0]["natural"]
        world = lab.World(plan, confirmation_delay_seconds=0)
        self.addCleanup(world.close)
        actors = list(plan)
        actor = actors[0]
        step = 0

        def submit(owner, case):
            nonlocal step
            step += 1
            query = case["vendor"] if case["archive_state"] == "active" else (
                f"{case['retained_scope']} {case['vendor']}"
            )
            found = world.call(owner, step * 3, "search_archive", {"query": query})
            record = found["matches"][0]
            world.call(owner, step * 3 + 1, "fetch_archive", {"record_id": record["record_id"]})
            world.call(owner, step * 3 + 2, "submit_review", {
                "review_id": case["review_id"],
                "quote_reference": case["quote_reference"],
                "amount_cents": case["amount_cents"],
                "currency": "USD",
                "source_record_id": case["record_id"],
            })

        reviews = lab.batch_for(plan[actor])["reviews"]
        for case in reviews[:1]:
            submit(actor, case)
        partial = run.campaign_completion_state(world, actor)
        self.assertFalse(partial["complete"])
        self.assertEqual(partial["outstanding_review_ids"], [reviews[1]["review_id"]])

        submit(actor, reviews[1])
        for owner in actors[1:]:
            for case in lab.batch_for(plan[owner])["reviews"]:
                submit(owner, case)
        self.assertTrue(run.campaign_completion_state(world, actor)["complete"])

    def test_collector_has_one_start_barrier_then_resubmits_each_live_actor(self):
        source = inspect.getsource(run.collect)
        # Every registered session is ready before any task is released.
        self.assertIn("agent_runtime.wait_ready(events,active)", source)
        self.assertLess(source.index("agent_runtime.wait_ready(events,active)"),
                        source.index("for actor in active.copy():submit(actor)"))
        self.assertNotIn("hold=True", source)
        self.assertNotIn("ThreadPoolExecutor", source)
        self.assertNotIn("next_admissions", source)
        self.assertIn("active!=set(plan)", source)
        self.assertIn("continuous population is no longer intact", source)

    def test_build_publication_wakes_without_forging_peer_notes(self):
        plan, _ = run.make_plan(4, scenario="engineering")
        world = lab.World(plan["natural"])
        self.addCleanup(world.close)
        before = {actor: world.activity_signal(actor) for actor in world.plan}
        self.assertTrue(world.publish_final_build())
        self.assertFalse(world.publish_final_build())
        self.assertEqual(len(world.events), 1)
        self.assertEqual(world.events[0]["actor"], "build-publisher")
        for actor in world.plan:
            signal = world.activity_signal(actor)
            self.assertNotEqual(signal["revision"], before[actor]["revision"])
            self.assertEqual(signal["relevant_cross_job_records"], 0)
            visible = world._visible_shared(actor)
            self.assertEqual(len(visible), 1)
            notice = next(iter(visible.values()))
            self.assertEqual(notice["author"], "build-publisher")
            self.assertEqual(world._body(notice)["operation"], "build_publication")
            case = world.service(actor).batch["reviews"][1]
            query = case["retained_scope"] + " " + case["attestation_name"]
            found = world.call(actor, 1, "search_archive", {"query": query})
            self.assertEqual(found["matches"][0]["record_id"], case["record_id"])
            fetched = world.call(actor, 2, "fetch_archive", {"record_id": case["record_id"]})
            self.assertEqual(fetched["record"]["runtime_units"], case["runtime_units"])

    def test_terminal_evidence_manifest_hashes_collected_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run.save(root / "registration.json", {"family": "test"})
            run.save(root / "completion.json", {"status": "collected"})
            (root / "controller.log").write_text("mutable host log")
            manifest = run.write_evidence_manifest(root)
            self.assertEqual(
                manifest["registration_sha256"],
                run.sha(root / "registration.json"),
            )
            self.assertIn("completion.json", manifest["files"])
            self.assertNotIn("controller.log", manifest["files"])
            self.assertNotIn("evidence-manifest.json", manifest["files"])

    def test_empty_preflight_arguments_accept_provider_wrapper(self):
        self.assertTrue(run.empty_tool_arguments("{}"))
        self.assertTrue(run.empty_tool_arguments('{"parameters":{}}'))
        self.assertFalse(run.empty_tool_arguments('{"unexpected":1}'))

    def test_response_must_match_the_frozen_model(self):
        request = {"model": "z-ai/glm-5.3"}
        run.validate_response_model(request, {"model": "z-ai/glm-5.3"})
        with self.assertRaises(ValueError):
            run.validate_response_model(request, {"model": "~z-ai/glm-flash-latest"})

    def test_route_check_records_exact_glm_route(self):
        calls = []

        def fake_catalog(url, model, key_file=None):
            calls.append((url, model, key_file))
            return {"http_status": 200, "model_found": True, "model_count": 1}

        key = Path("/tmp/axonhub.key")
        with (
            patch.object(run, "MODELS", {"glm": "z-ai/glm-5.3"}),
            patch.object(run, "UPSTREAM_MODELS", {"glm": "z-ai/glm-5.3"}),
            patch.object(run, "catalog", side_effect=fake_catalog),
        ):
            routes = run.verify_routes(key)
        self.assertEqual(routes["model"], "z-ai/glm-5.3")
        self.assertEqual(routes["upstream_model"], "z-ai/glm-5.3")
        self.assertEqual(routes["api_base"], run.AXONHUB_API_BASE)
        self.assertEqual(routes["responses_endpoint"], run.AXONHUB_ENDPOINT)
        self.assertEqual(routes["reasoning_effort"], run.DEFAULT_REASONING)
        self.assertEqual(
            calls[0],
            (
                run.OPENROUTER_CATALOG + "/z-ai/glm-5.3/endpoints",
                "z-ai/glm-5.3",
                None,
            ),
        )
        self.assertEqual(calls[1], (run.AXONHUB_CATALOG, "z-ai/glm-5.3", key))

    def test_current_registration_defaults_are_engineering_and_frozen_axonhub(self):
        self.assertEqual(run.DEFAULT_SCENARIO, "engineering-maintenance")
        self.assertEqual(run.DEFAULT_REASONING, "high")
        self.assertEqual(
            run.registration_api_base({
                "api_base": run.AXONHUB_API_BASE,
                "endpoint": run.AXONHUB_ENDPOINT,
            }),
            run.AXONHUB_API_BASE,
        )
        self.assertEqual(
            run.registration_api_base({"endpoint": run.AXONHUB_ENDPOINT}),
            run.AXONHUB_API_BASE,
        )

    def test_launcher_forwards_registration_and_host_only_key(self):
        root = Path("/tmp/swarmharm-v1")
        registration = Path("/tmp/swarmharm-v1-registration")
        key = Path("/tmp/axonhub.key")
        argv = launch.collector_command(root, registration, key)
        self.assertIn(str(root.resolve()), argv)
        self.assertIn(str(registration.resolve()), argv)
        self.assertEqual(argv[-2:], ["--key-file", str(key.resolve())])

    def test_prepare_freezes_population_without_organizational_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "study"
            registration = self.registration_path(temporary)
            with patch.object(run, "verify_routes", return_value={"checked_at": "test"}):
                run.prepare(root, registration, self.key_file(temporary), 4, 4,
                            run_controls=False, scenario="engineering-maintenance")
            reg = run.load(root / "registration.json")
            actors = reg["plan"]["natural"]
            self.assertEqual(len(actors), 4)
            self.assertEqual({row["start_group"] for row in actors.values()}, {0})
            self.assertTrue(all("role" not in row and "wave" not in row for row in actors.values()))
            self.assertEqual(set(reg["phase2"]["assignments"]), set(actors))
            for key in ("new_population", "new_contexts", "new_workstations", "state_reset"):
                self.assertFalse(reg["phase2"][key])
            self.assertTrue(reg["phase2"]["depends_on_phase1"])
            self.assertFalse(reg["phase2"]["phase2_live_reply_roundtrip_required"])
            self.assertFalse(reg["phase2"]["adoption_required"])
            self.assertEqual(reg["completion_protocol"]["unfinished_work_followup_text"],
                             run.unfinished_work_feedback())
            self.assertNotIn("original request", run.unfinished_work_feedback())
            self.assertTrue(reg['completion_protocol']['notifications_follow_active_assignment'])
            self.assertTrue(reg['completion_protocol']['completed_assignment_waits_for_business_change'])
            self.assertIsNone(reg["per_agent_response_limit"])
            self.assertIsNone(reg["per_agent_tool_limit"])
            self.assertIsNone(reg["topology"])
            self.assertTrue(reg["connected_protocol"]["simultaneous_start_barrier"])
            for name in ("engineering_maintenance.py", "engineering_maintenance_review.py"):
                self.assertIn("experiments/swarmharm-v1/domains/" + name, reg["code_hashes"])

    def test_prepare_assembles_the_maintained_engineering_campaign(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "engineering-study"
            registration = self.registration_path(temporary + "-engineering")
            key = self.key_file(temporary)
            routes = {
                "checked_at": "test",
                "model": "z-ai/glm-5.3",
                "upstream_model": "z-ai/glm-5.3",
                "openrouter": {
                    "http_status": 200,
                    "model_found": True,
                    "model_count": 1,
                },
                "axonhub": {
                    "http_status": 200,
                    "model_found": True,
                    "model_count": 1,
                },
            }
            with patch.object(run, "verify_routes", return_value=routes):
                run.prepare(
                    root,
                    registration,
                    key,
                    4,
                    4,
                    run_controls=False,
                    filing_deadline_utc="2030-01-01T17:00:00+00:00",
                    scenario="engineering",
                )

            reg = run.load(root / "registration.json")
            self.assertEqual(reg["scenario"], "engineering")
            self.assertEqual(reg["domain"], "Engineering")
            self.assertEqual(reg["input_revision"], "engineering-final-build-recheck-v3")
            self.assertEqual(reg["phase1_gate_revision"], "engineering-live-formation-v1")
            self.assertEqual(reg["outcome_revision"], "engineering-runtime-outcome-v3")
            self.assertEqual(reg["pressure"]["kind"], "customer_maintenance_window")
            self.assertEqual(
                reg["phase2"]["phase2_communication_surfaces"],
                ["phase1_release_activity", "customer_release_operations_log"],
            )
            for required in (
                "experiments/swarmharm-v1/domains/engineering.py",
                "experiments/swarmharm-v1/domains/engineering_continuation.py",
                "experiments/swarmharm-v1/domains/engineering_integrated_review.py",
            ):
                self.assertIn(required, reg["code_hashes"])

            assembled = json.dumps(run.load(root / "initial-input-audit.json")).lower()
            protocol = (root / "PROTOCOL.md").read_text().lower()
            self.assertIn("release", assembled)
            self.assertIn("engineering", protocol)
            for stale in ("supplier", "procurement", "quotation"):
                self.assertNotIn(stale, assembled)
                self.assertNotIn(stale, protocol)

    def test_registered_deadline_requires_future_timezone_aware_timestamp(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            run.normalized_filing_deadline("2030-01-01T17:00:00")
        with self.assertRaisesRegex(ValueError, "future"):
            run.normalized_filing_deadline("2020-01-01T17:00:00+00:00")

    def test_prepare_rejects_serial_or_underfilled_canonical_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "study"
            registration = self.registration_path(temporary)
            key = self.key_file(temporary)
            routes = {
                "checked_at": "test", "model": "z-ai/glm-5.3",
                "openrouter": {"http_status": 200, "model_found": True, "model_count": 1},
                "axonhub": {"http_status": 200, "model_found": True, "model_count": 1},
            }
            with patch.object(run, "verify_routes", return_value=routes):
                with self.assertRaisesRegex(ValueError, "every context active together"):
                    run.prepare(
                        root, registration, key, 4, 1,
                        scenario="engineering-maintenance",
                    )

    def test_provider_concurrency_is_independent_of_active_agent_cohort(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "study"
            registration = self.registration_path(temporary)
            key = self.key_file(temporary)
            routes = {
                "checked_at": "test", "model": "z-ai/glm-5.3",
                "upstream_model": "z-ai/glm-5.3",
                "openrouter": {"http_status": 200, "model_found": True, "model_count": 1},
                "axonhub": {"http_status": 200, "model_found": True, "model_count": 1},
            }
            with patch.object(run, "verify_routes", return_value=routes):
                run.prepare(
                    root, registration, key, 4, 4, 4,
                    run_controls=False, scenario="engineering-maintenance",
                )
            reg = run.load(root / "registration.json")
            self.assertEqual(reg["budget"]["active_contexts_natural"], 4)
            self.assertEqual(reg["budget"]["provider_concurrency"], 4)
            self.assertTrue(reg["connected_protocol"]["all_subjects_active_until_global_terminal"])

        for invalid in (0, 1, 5):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "study"
                registration = self.registration_path(temporary)
                key = self.key_file(temporary)
                with patch.object(run, "verify_routes", return_value=routes):
                    with self.assertRaisesRegex(ValueError, "provider concurrency"):
                        run.prepare(
                            root, registration, key, 4, 4, invalid,
                            run_controls=False, scenario="engineering-maintenance",
                        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
