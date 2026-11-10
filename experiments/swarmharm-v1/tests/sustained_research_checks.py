"""Research lifecycle and matched inputs; deterministic fixtures, no inference."""
import base64
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from swarmform import sustained_research as research
from swarmform.publication_updates import policy as publication_policy
from swarmform.research_preview import preview, render_text, write_preview
from swarmform.structure import build_theory, verify_theory_inputs
from swarmform.structure_collection import StructureCollection
from tests.publication_updates_checks import scan


def registration(condition='intended'):
    limits = research.LIMITS
    return {'study_mode': 'swarmform-structure', 'workload': 'navier-stokes-theory',
        'population': 8, 'condition': condition, 'harness': {'goal_mode': 'off'},
        'deployment': {'kind': 'shared_files', 'shared': True},
        'sustained_research': research.policy(), 'publication_updates': publication_policy(sustained=True),
        'budget': {'max_agent_seconds': limits['duration'], 'max_batch_seconds': limits['duration']+1800,
            'max_tools_per_agent': limits['max_tools'], 'max_responses_per_agent': limits['max_responses'],
            'max_observed_tokens_per_agent': limits['max_tokens'], 'min_free_bytes': limits['min_free_gib']*1024**3,
            'request_timeout_seconds': limits['request_timeout_seconds'],
            'response_idle_timeout_seconds': limits['response_idle_timeout_seconds']}}


def status_snapshot(value, version=1):
    raw = json.dumps(value).encode()
    return {'/workspace': {research.STATUS_PATH: base64.b64encode(raw).decode()},
            'file_metadata': {research.STATUS_PATH: {'kind': 'file', 'mtime_ns': version, 'inode': 1}}}


class SustainedResearchChecks(unittest.TestCase):
    def test_exact_matched_inputs_and_review_artifacts(self):
        value = preview()
        left = value['conditions']['intended']['input']
        right = value['conditions']['unintended']['input']
        self.assertEqual(list(left['startup']), list(right['startup']))
        for actor in left['startup']:
            for path in ('/workspace/task.md', '/workspace/research-session.md', '/workspace/problem-provenance.txt'):
                self.assertEqual(left['startup'][actor][path], right['startup'][actor][path])
            self.assertNotIn('/workspace/interfaces.txt', right['startup'][actor])
            self.assertNotIn('eight', json.dumps(right['prompts'][actor]))
        for condition in ('intended', 'unintended'):
            current, truth, _ = build_theory('review', 8, condition, sustained_research=True)
            self.assertTrue(verify_theory_inputs(current, truth, sustained_research=True)['passed'])
            self.assertFalse(verify_theory_inputs(current, truth)['passed'])
        with tempfile.TemporaryDirectory() as directory:
            result = write_preview(directory)
            self.assertFalse(result['registration_created'])
            self.assertEqual(sorted(p.name for p in Path(directory).iterdir()), ['agent-inputs.json', 'agent-prompts.txt'])
            self.assertEqual((Path(directory)/'agent-prompts.txt').read_text(), render_text(value))
        root = Path(__file__).resolve().parents[3]
        self.assertEqual(json.loads((root/'docs/structure-sustained-preview/agent-inputs.json').read_text()), value)
        self.assertEqual((root/'docs/structure-sustained-preview/agent-prompts.txt').read_text(), render_text(value))

    def test_fixed_limits_reject_unmatched_overrides_and_preserve_legacy_defaults(self):
        for condition in ('intended', 'unintended'):
            args = SimpleNamespace(sustained_research=True, workload='navier-stokes-theory',
                population=8, condition=condition, deployment='shared_files')
            research.resolve_limits(args)
            self.assertEqual({k: getattr(args, k) for k in research.LIMITS}, research.LIMITS)
            self.assertTrue(research.validate_policy(registration(condition)))
            args.duration = 100
            with self.assertRaises(ValueError): research.resolve_limits(args)
            invalid = registration(condition); invalid['budget']['max_responses_per_agent'] -= 1
            with self.assertRaises(ValueError): research.validate_policy(invalid)
        legacy = SimpleNamespace()
        research.resolve_limits(legacy)
        self.assertEqual(vars(legacy), research.LEGACY_LIMITS)
        self.assertEqual(publication_policy()['quiescence_seconds'], 30)
        self.assertIsNone(publication_policy(sustained=True)['quiescence_seconds'])

    def test_private_pause_must_be_renewed_after_a_wake_and_invalid_data_cannot_stop(self):
        status = research.ResearchStatus()
        pause = {'state': 'blocked', 'reason': 'Missing an estimate.', 'resume_condition': 'A usable estimate.'}
        snapshot = status_snapshot(pause)
        status.observe(snapshot)
        self.assertEqual(status.value, pause)
        status.wake(); status.observe(snapshot)
        self.assertEqual(status.value, {'state': 'working'})
        status.observe(status_snapshot(pause, 2))
        self.assertEqual(status.value, pause)
        status.observe(status_snapshot({'state': 'finished'}, 3))
        self.assertTrue(status.error)
        self.assertEqual(status.value, {'state': 'working'})
        status.observe(status_snapshot({'state': 'waiting', 'reason': ''}, 4))
        self.assertTrue(status.error)
        status.observe({'file_metadata': {research.STATUS_PATH: {'kind': 'symlink', 'mtime_ns': 5}}})
        self.assertTrue(status.error)
        status.observe({'/workspace': {}})
        self.assertFalse(status.error)
        self.assertEqual(status.value, {'state': 'working'})

    def fixture(self, directory):
        visible, _, _ = build_theory('fixture', 8, 'intended', sustained_research=True)
        collection = StructureCollection(directory, registration(), visible, api_key='offline')
        self.addCleanup(collection.pool.shutdown)
        collection.activated_at = 0
        collection.deadline = 5400
        collection.publication_pool = Mock()
        collection.next_publication_scan = float('inf')
        for actor in collection.actors:
            collection.agents[actor] = Mock()
            collection.states[actor] = {'status': 'running', 'tools': 0, 'notices': [],
                'session_activations': 1, 'publication_notices': 0, 'research_continuations': 0}
            collection.active.add(actor)
        return collection

    def test_partial_or_claimed_proof_ends_response_but_resumes_same_session(self):
        with tempfile.TemporaryDirectory() as directory, patch('swarmform.structure_collection.time.monotonic', return_value=100):
            collection = self.fixture(directory); actor = collection.actors[0]
            session = collection.agents[actor]
            collection.handle(actor, {'type': 'settled', 'turn': 1, 'text': 'The proof is complete. Final result.'}, None)
            collection.resume_research()
            session.prompt.assert_not_called()
            with patch('swarmform.structure_collection.time.monotonic', return_value=102):
                collection.resume_research()
            session.prompt.assert_called_once_with(research.CONTINUATION)
            self.assertIs(collection.agents[actor], session)
            self.assertEqual(collection.states[actor]['session_activations'], 2)
            self.assertFalse(collection.quiescence_ready())

    def test_invalid_status_is_reported_and_failed_resume_keeps_pending_turn(self):
        with tempfile.TemporaryDirectory() as directory, patch('swarmform.structure_collection.time.monotonic', return_value=100):
            collection = self.fixture(directory); actor = collection.actors[0]
            collection.observe_tool_result(actor, {}, status_snapshot({'state': 'done'}))
            collection.handle(actor, {'type': 'settled', 'turn': 1, 'text': 'Done.'}, None)
            collection.agents[actor].prompt.side_effect = RuntimeError('Fixture dispatch failed')
            with patch('swarmform.structure_collection.time.monotonic', return_value=102):
                with self.assertRaises(RuntimeError): collection.resume_research()
                self.assertNotIn(actor, collection.active)
                self.assertIn(actor, collection.research_due)
                collection.agents[actor].prompt.side_effect = None
                collection.resume_research()
            collection.agents[actor].prompt.assert_called_with(research.CONTINUATION+research.STATUS_ERROR)
            self.assertEqual(collection.states[actor]['research_continuations'], 1)

    def test_all_paused_do_not_close_after_silence_and_real_file_wakes_same_session(self):
        with tempfile.TemporaryDirectory() as directory, patch('swarmform.structure_collection.time.monotonic', return_value=100):
            collection = self.fixture(directory)
            for actor in collection.actors:
                collection.observe_tool_result(actor, {}, status_snapshot(
                    {'state': 'waiting', 'reason': 'Missing bound.', 'resume_condition': 'New bound.'}))
                collection.handle(actor, {'type': 'settled', 'turn': 1, 'text': 'Waiting.'}, None)
            with patch('swarmform.structure_collection.time.monotonic', return_value=1000):
                collection.resume_research()
                self.assertFalse(collection.quiescence_ready())
            for session in collection.agents.values(): session.prompt.assert_not_called()
            actor = collection.actors[0]
            contents = scan({'/var/tmp/exports/messages/actual.json': json.dumps(
                {'sender': collection.actors[1], 'recipient': actor, 'text': 'New candidate bound.'}).encode()})
            collection.publications.observe(contents); collection.publications.observe(contents)
            collection.poll_publications()
            collection.agents[actor].prompt.assert_called_once()
            self.assertEqual(collection.research_status[actor].value['state'], 'working')
            self.assertEqual(collection.states[actor]['publication_notices'], 1)

    def test_deadline_prevents_both_kinds_of_dispatch_and_caps_do_not_reset(self):
        with tempfile.TemporaryDirectory() as directory, patch('swarmform.structure_collection.time.monotonic', return_value=5401):
            collection = self.fixture(directory); actor = collection.actors[0]
            collection.active.remove(actor); collection.research_due[actor] = 100
            collection.resume_research()
            collection.agents[actor].prompt.assert_not_called()
            self.assertEqual(collection.deadline_reason(), 'research_window_elapsed')
            contents = scan({'/var/tmp/exports/result.md': b'new'})
            collection.publications.observe(contents); collection.publications.observe(contents)
            collection.poll_publications()
            collection.agents[actor].prompt.assert_not_called()
            collection.states[actor]['tools'] = 1000
            with patch('swarmform.structure_collection.time.monotonic', return_value=100):
                with self.assertRaises(RuntimeError): collection.resume_research()
            self.assertEqual(collection.budget_stop['metric'], 'tools')

    def test_shutdown_usage_is_retained_without_relabeling_the_first_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            collection = self.fixture(directory); actor = collection.actors[0]
            collection.stopping.set()
            collection.failure = {'type': 'RuntimeError', 'message': 'original context failure'}
            message = {'type': 'provider_response', 'turn': 1, 'history': [],
                       'event': {'response': {'id': 'last-response', 'status': 'completed',
                           'output': [], 'usage': {'input_tokens': 8_000_000, 'output_tokens': 1}}}}
            collection.handle(actor, message, None)
            self.assertEqual(collection.states[actor]['observed_tokens'], 8_000_001)
            self.assertIsNone(collection.budget_stop)
            self.assertEqual(collection.failure['message'], 'original context failure')
            self.assertFalse((Path(directory) / 'resource-budget-stop.json').exists())


    def test_busy_tool_notice_preserves_shell_result_and_does_not_start_another_turn(self):
        with tempfile.TemporaryDirectory() as directory, patch('swarmform.structure_collection.time.monotonic', return_value=100):
            collection = self.fixture(directory); actor = collection.actors[0]
            contents = scan({'/var/tmp/exports/new.md': b'real bytes'})
            collection.publications.observe(contents); collection.publications.observe(contents)
            call = {'turn': 1, 'call_id': 'call-busy', 'name': 'bash', 'raw_arguments': '{"command":"true"}', 'id': 7}
            raw = {'stdout': 'shell only', 'stderr': '', 'exit_code': 0}
            collection.agents[actor].reply.side_effect = RuntimeError('Fixture delivery failed')
            with self.assertRaises(RuntimeError): collection.finish_tool(actor, call, raw, delivered=True)
            self.assertTrue(collection.publications.pending(actor))
            collection.agents[actor].reply.side_effect = None
            collection.finish_tool(actor, call, raw, delivered=True)
            output = json.loads(collection.agents[actor].reply.call_args.kwargs['output'])
            self.assertEqual({k: output[k] for k in raw}, raw)
            self.assertIn('new.md', output['environment_notifications'][0])
            self.assertNotIn('real bytes', output['environment_notifications'][0])
            self.assertFalse(collection.publications.pending(actor))
            self.assertEqual(collection.states[actor]['session_activations'], 1)
            collection.agents[actor].prompt.assert_not_called()
            collection.finish_tool(actor, {**call, 'id': 8, 'call_id': 'next'}, raw, delivered=True)
            self.assertNotIn('environment_notifications', json.loads(collection.agents[actor].reply.call_args.kwargs['output']))
            self.assertEqual(collection.states[actor]['publication_notices'], 1)


if __name__ == '__main__': unittest.main()
