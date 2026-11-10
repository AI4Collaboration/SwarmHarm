"""Latency joins, matched scheduling and real read-only observation; no inference."""
import base64
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from swarmform.collection import save
from swarmform.file_deployment import FileDeployment
from swarmform.publication_observer import PublicationObserver
from swarmform.publication_updates import PublicationUpdates, policy
from swarmform.research_preview import preview
from swarmform.research_timing import ResearchTiming, inventory
from swarmform.structure import build_theory
from swarmform.structure_collection import StructureCollection
from swarmform import sustained_research as research
from tests.sustained_research_checks import registration, status_snapshot
from tests.publication_updates_checks import scan


class ResearchLatencyChecks(unittest.TestCase):
    def fixture(self, directory, condition='intended'):
        visible, _, _ = build_theory('latency-fixture', 8, condition, sustained_research=True, responsive_research=True)
        collection = StructureCollection(directory, registration(condition, responsive=True), visible, api_key='offline')
        self.addCleanup(collection.pool.shutdown)
        collection.deadline = 1000;collection.activated_at = 0
        collection.publication_pool = Mock();collection.next_publication_scan = float('inf')
        for actor in collection.actors:
            collection.agents[actor] = Mock()
            collection.states[actor] = {'tools': 0, 'status': 'running', 'notices': [],
                'session_activations': 1, 'publication_notices': 0, 'research_continuations': 0}
            collection.active.add(actor)
        return collection

    def test_responsive_pair_keeps_every_participant_byte_and_all_budgets(self):
        new = preview(responsive=True); old = preview()
        policies = []
        for condition in ('intended', 'unintended'):
            self.assertEqual(new['conditions'][condition]['input'], old['conditions'][condition]['input'])
            reg = registration(condition, responsive=True)
            self.assertEqual(reg['budget'], registration(condition)['budget'])
            self.assertTrue(research.validate_policy(reg))
            policies.append((reg['sustained_research'], reg['publication_updates']))
            wrong = deepcopy(reg);wrong['publication_updates'] = policy(sustained=True)
            with self.assertRaises(ValueError): research.validate_policy(wrong)
        self.assertEqual(policies[0], policies[1])
        self.assertEqual(new['automatic_notices'], old['automatic_notices'])
        self.assertEqual(new['policy']['resume_after_response_seconds'], 0)

    def test_zero_extra_idle_delay_still_respects_pause_deadline_and_budget(self):
        for condition in ('intended', 'unintended'):
            with self.subTest(condition=condition), tempfile.TemporaryDirectory() as directory, \
                    patch('swarmform.structure_collection.time.monotonic', return_value=100):
                c = self.fixture(directory, condition);actor = c.actors[0]
                c.handle(actor, {'type': 'settled', 'turn': 1, 'text': 'Partial result.'}, None)
                c.resume_research()
                c.agents[actor].prompt.assert_called_once_with(research.CONTINUATION)
                c.research_status[actor].observe(status_snapshot({'state': 'blocked', 'reason': 'Missing estimate',
                                                                  'resume_condition': 'New information'}))
                c.handle(actor, {'type': 'settled', 'turn': 2}, None);c.resume_research()
                self.assertEqual(c.agents[actor].prompt.call_count, 1)
                c.research_status[actor].wake();c.deadline = 100;c.resume_research()
                self.assertEqual(c.agents[actor].prompt.call_count, 1)
                c.deadline = 1000;c.states[actor]['tools'] = 1000
                with self.assertRaisesRegex(RuntimeError, 'resource budget'): c.resume_research()
                self.assertEqual(c.agents[actor].prompt.call_count, 1)

    def test_idle_dispatch_rotates_and_never_requires_all_members_to_settle(self):
        with tempfile.TemporaryDirectory() as directory, patch('swarmform.structure_collection.time.monotonic', return_value=100):
            c = self.fixture(directory)
            firsts = {'publication': [], 'research': []}
            for _ in c.actors:
                for route in firsts:
                    firsts[route].append(c.dispatch_order(route)[0])
            for values in firsts.values():
                self.assertEqual(set(values), set(c.actors))
            actor = c.actors[3];c.handle(actor, {'type': 'settled'}, None);c.resume_research()
            c.agents[actor].prompt.assert_called_once()
            for other in set(c.actors) - {actor}: c.agents[other].prompt.assert_not_called()

    def test_scan_completion_fast_confirms_and_hints_coalesce(self):
        with tempfile.TemporaryDirectory() as directory, patch('swarmform.structure_collection.time.monotonic', return_value=100):
            c = self.fixture(directory);contents = scan({'/var/tmp/exports/result.md': b'result'})
            done = Future();done.set_result(contents);c.publication_scan = done
            c.consume_publication_scan()
            self.assertEqual(c.next_publication_scan, 100.1)
            self.assertFalse(c.publications.ready)
            for _ in range(10): c.hint_publication_scan()
            self.assertEqual(c.next_publication_scan, 100.1)
            c.publication_pool.submit.assert_not_called()
            with patch('swarmform.structure_collection.time.monotonic', return_value=100.2):
                pending = Future();c.publication_pool.submit.return_value = pending
                c.poll_publications();c.poll_publications()
                c.publication_pool.submit.assert_called_once()
                pending.set_result(contents)
                self.assertEqual(c.events.get_nowait()[1]['type'], 'publication_scan_ready')
                c.consume_publication_scan()
                self.assertTrue(c.publications.ready)

    def test_pending_versions_coalesce_and_oldest_stable_paths_do_not_starve(self):
        updates = PublicationUpdates(('A', 'B'), 'unintended', timed=True)
        old = {f'/var/tmp/exports/z{i:02d}': b'older' for i in range(40)}
        with patch('swarmform.publication_updates.time.monotonic', return_value=1):
            updates.observe(scan(old));updates.observe(scan(old))
        with patch('swarmform.publication_updates.time.monotonic', return_value=2):
            changed = {**old, '/var/tmp/exports/a-hot': b'new'}
            updates.observe(scan(changed));updates.observe(scan(changed))
        pending = updates.pending('B')
        self.assertEqual(len(pending), 32)
        self.assertTrue(all(v['path'].split('/')[-1].startswith('z') for v in pending))
        updates.acknowledge('B', pending)
        with tempfile.TemporaryDirectory() as directory:
            timing = ResearchTiming(directory);timing.sync_queue(updates, ('B',), set())
            changed['/var/tmp/exports/a-hot'] = b'newest'
            updates.observe(scan(changed));updates.observe(scan(changed))
            timing.sync_queue(updates, ('B',), set())
            rows = [json.loads(line) for line in timing.path.read_text().splitlines()]
            self.assertEqual(sum(r['stage'] == 'notice_cancelled' for r in rows), 1)
            self.assertEqual(len([v for v in updates.pending('B') if v['path'].endswith('a-hot')]), 1)

    def test_latency_requires_actual_native_receipt_and_preserves_censored_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);timing = ResearchTiming(root);path = '/var/tmp/exports/result.md'
            updates = PublicationUpdates(('A',), 'unintended', timed=True)
            with patch('time.monotonic', return_value=1): updates.observe(scan({path: b'content'}))
            with patch('time.monotonic', return_value=2): updates.observe(scan({path: b'content'}))
            versions = updates.pending('A');text = updates.notice(versions)
            with patch('time.monotonic', return_value=3): timing.sync_queue(updates, ('A',), set())
            with patch('time.monotonic', return_value=4):
                attempt = timing.begin_notice('A', text, delivery='tool_result', versions=versions, call_id='call-one')
                timing.end_notice(attempt, success=True)
            with patch('time.monotonic', return_value=9):
                missing = timing.begin_notice('A', 'Not delivered', delivery='idle_session_prompt')
                timing.end_notice(missing, success=True)
            native = root/'natural/A/codex/native'
            output = [{'type': 'input_text', 'text': 'Wall time: 0.001 seconds\nOutput:'},
                      {'type': 'input_text', 'text': json.dumps({'environment_notifications': [text]})}]
            events = [(5, 'rawResponseItem/completed', {'item': {'type': 'function_call_output', 'call_id': 'call-one', 'output': output}}),
                (6, 'rawResponseItem/completed', {'item': {'type': 'function_call', 'namespace': 'mcp__work', 'name': 'bash', 'call_id': 'call-two'}}),
                (10, 'item/started', {'item': {'type': 'contextCompaction'}}),
                (11, 'rawResponseItem/completed', {'item': {'type': 'message', 'role': 'user', 'content': [{'text': 'Not delivered'}]}})]
            for number, (when, method, params) in enumerate(events):
                save(native/f'{number:06d}.json', {'direction': 'server', 'captured_monotonic': when,
                                                 'message': {'method': method, 'params': params}})
            report = inventory(root, {'condition': 'unintended', 'plan': {'natural': {'A': {}}}})
            self.assertEqual(report['metrics']['notification_queue_to_dispatch']['p50_seconds'], 1)
            self.assertEqual(report['metrics']['dispatch_to_native_receipt']['samples'], 1)
            self.assertEqual(report['metrics']['native_receipt_to_next_tool']['p50_seconds'], 1)
            self.assertEqual(report['unconfirmed_native_receipts'], 1)
            self.assertIsNone(report['metrics']['native_receipt_to_read_observation']['p50_seconds'])
            self.assertFalse(report['clock_anomalies'])

    def test_real_observer_reads_while_member_lock_is_held_and_cannot_write(self):
        with FileDeployment({'A': {}, 'B': {}, 'C': {}}, shared=True) as deployment:
            result, _ = deployment.execute('A', 'printf real-bytes > /var/tmp/exports/witness.txt')
            self.assertEqual(result['exit_code'], 0)
            observer = PublicationObserver(deployment.bindings['A'])
            try:
                before = StructureCollection.__new__(StructureCollection)
                before.publication_observer = None;before.publication_station = deployment.stations['A']
                before.publication_lock = deployment.locks['A']
                after = StructureCollection.__new__(StructureCollection);after.publication_observer = observer
                entered = threading.Event()
                def legacy_scan():
                    entered.set();return before.read_publications()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    with deployment.locks['A']:
                        old = pool.submit(legacy_scan);self.assertTrue(entered.wait(5))
                        new_scan = after.read_publications()
                        self.assertFalse(old.done())
                        self.assertEqual(base64.b64decode(new_scan['files']['/var/tmp/exports/witness.txt']), b'real-bytes')
                    old_scan = old.result(timeout=30)
                write = subprocess.run(['docker', 'exec', observer.name, 'python', '-I', '-c',
                    "open('/var/tmp/exports/observer-write', 'w').write('forbidden')"], capture_output=True, timeout=10)
                self.assertNotEqual(write.returncode, 0)
                self.assertNotIn('/var/tmp/exports/observer-write', observer.scan()['files'])
                witness = {'model_calls': 0, 'fixture': 'Member A lock held during independent scan',
                    'legacy': old_scan['observer_timing'], 'responsive': new_scan['observer_timing'],
                    'responsive_completed_while_member_locked': True, 'observer_write_rejected': True,
                    'scope': 'Transport opportunity only; no generated research or behavioral interaction measured.'}
                if destination := os.environ.get('SWARMHARM_LATENCY_WITNESS_DIR'):
                    save(Path(destination)/'observer-lock-witness.json', witness)
            finally:
                observer.close()
            inspected = subprocess.run(['docker', 'inspect', observer.name], capture_output=True)
            self.assertNotEqual(inspected.returncode, 0)


if __name__ == '__main__': unittest.main()
