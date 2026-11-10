"""Continuation races and evidence receipts, with no model calls."""
import base64
from concurrent.futures import Future
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from swarmform.collection import save
from swarmform.publication_updates import PublicationUpdates, SCAN, policy, validate_policy
from swarmform.structure import build_theory, verify_theory_inputs
from swarmform.structure_collection import StructureCollection


def scan(files):
    return {'stable': True, 'files': {p: base64.b64encode(v).decode() for p, v in files.items()}}


def envelope(recipient='B', text='Check this new result.'):
    return json.dumps({'sender': 'A', 'recipient': recipient, 'text': text}).encode()


def observation(root, records):
    root.mkdir(exist_ok=True)
    blobs = root/'blobs'; blobs.mkdir(exist_ok=True)
    lines = []
    for op, path, raw in records:
        encoded = ''.join('\\x%02x' % b for b in raw)
        lines.append(f'123 1000.000001 {op}(3<{path}>, "{encoded}", {len(raw)}) = {len(raw)}\n')
    data = ''.join(lines).encode(); digest = sha256(data).hexdigest()
    (blobs/digest).write_bytes(data)
    manifest = root/'capture.json'
    save(manifest, {'files': {'000001.log': {'sha256': digest, 'blob': 'blobs/'+digest}}})
    return {'path': str(manifest), 'sha256': sha256(manifest.read_bytes()).hexdigest()}


class PublicationChecks(unittest.TestCase):
    def test_registered_opt_in_preserves_legacy_and_same_task_without_roles(self):
        for condition in ('intended', 'unintended'):
            legacy, truth, old = build_theory('same', 8, condition)
            current, new_truth, new = build_theory('same', 8, condition, publication_updates=True)
            self.assertEqual(truth, new_truth)
            self.assertEqual(legacy['prompts'], current['prompts'])
            self.assertFalse(old['effective_settings']['communication_wakes_models'])
            self.assertTrue(new['effective_settings']['communication_wakes_models'])
            self.assertTrue(verify_theory_inputs(current, truth, publication_updates=True)['passed'])
            self.assertFalse(verify_theory_inputs(current, truth)['passed'])
            for actor in current['startup']:
                self.assertEqual(legacy['startup'][actor]['/workspace/task.md'], current['startup'][actor]['/workspace/task.md'])
        self.assertFalse(validate_policy({}))
        with self.assertRaises(ValueError): validate_policy({'publication_updates': policy()})

    def test_debounce_duplicate_reads_rewrites_and_new_version(self):
        updates = PublicationUpdates(('A', 'B'), 'intended')
        path = '/var/tmp/exports/messages/question.json'
        first = scan({path: envelope()})
        self.assertEqual(updates.observe(first), [])
        self.assertEqual(updates.pending('B'), [])
        updates.observe(first)
        notice = updates.pending('B')
        self.assertEqual(len(notice), 1)
        self.assertEqual(updates.pending('A'), [])
        updates.acknowledge('B', notice)
        for _ in range(5):
            self.assertEqual(updates.observe(first), [])
            self.assertEqual(updates.pending('B'), [])
        second = scan({path: envelope(text='The result has been corrected.')})
        updates.observe(second)
        self.assertEqual(updates.pending('B'), [])
        updates.observe(second)
        self.assertNotEqual(updates.pending('B'), notice)

    def test_busy_receipts_and_own_atomic_publication_do_not_wake_again(self):
        updates = PublicationUpdates(('A', 'B', 'C'), 'unintended')
        path = '/var/tmp/exports/navier-stokes/research.md'; raw = b'An actual partial result.'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            updates.accessed('A', observation(root/'a', [('write', path+'.tmp', raw)]))
            updates.accessed('B', observation(root/'b', [('read', path, raw)]))
            updates.observe(scan({path: raw})); updates.observe(scan({path: raw}))
            self.assertEqual(updates.pending('A'), [])
            self.assertEqual(updates.pending('B'), [])
            self.assertEqual(len(updates.pending('C')), 1)
            # Reading the old bytes cannot suppress a subsequently changed file.
            changed = scan({path: raw+b' Corrected.'})
            updates.observe(changed); updates.observe(changed)
            self.assertEqual(len(updates.pending('B')), 1)

    def test_unstable_or_removed_version_is_never_delivered_as_current(self):
        updates = PublicationUpdates(('A', 'B'), 'unintended')
        path = '/var/tmp/exports/result.md'
        updates.observe(scan({path: b'one'})); updates.observe(scan({path: b'one'}))
        updates.observe(scan({path: b'two'}))
        self.assertEqual(updates.pending('B'), [])
        updates.observe({'stable': False, 'files': {}})
        self.assertEqual(updates.pending('B'), [])
        updates.observe(scan({})); updates.observe(scan({}))
        self.assertEqual(updates.pending('B'), [])

    def test_unintended_does_not_acquire_an_addressing_convention(self):
        path = '/var/tmp/exports/messages/new.json'; contents = scan({path: envelope()})
        intended = PublicationUpdates(('A', 'B', 'C'), 'intended')
        unintended = PublicationUpdates(('A', 'B', 'C'), 'unintended')
        for updates in (intended, unintended):
            updates.observe(contents); updates.observe(contents)
        self.assertEqual(intended.pending('C'), [])
        self.assertEqual(len(unintended.pending('C')), 1)
        text = unintended.notice(unintended.pending('C'))
        self.assertNotIn('sender', text)
        self.assertNotIn('Check this new result', text)
        self.assertNotIn('Research', text)

    def test_scan_reads_real_files_and_does_not_follow_symlinks_or_block_on_fifo(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); public = root/'public'; public.mkdir()
            (public/'real.txt').write_text('actual content')
            (root/'private.txt').write_text('must not be scanned')
            (public/'link').symlink_to(root/'private.txt')
            (public/'dir-link').symlink_to(root, target_is_directory=True)
            __import__('os').mkfifo(public/'fifo')
            config = {**policy(), 'root': str(public)}
            response = subprocess.run([sys.executable, '-I', '-c', SCAN], input=json.dumps(config),
                                      text=True, capture_output=True, check=True, timeout=5)
            result = json.loads(response.stdout)
            self.assertTrue(result['stable'])
            self.assertEqual(set(result['files']), {str(public/'real.txt')})
            self.assertEqual(base64.b64decode(result['files'][str(public/'real.txt')]), b'actual content')

    def test_tampered_observation_and_outside_publication_are_rejected(self):
        updates = PublicationUpdates(('A', 'B'), 'unintended')
        with self.assertRaises(ValueError): updates.observe(scan({'/workspace/private': b'private'}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ref = observation(root/'trace', [('read', '/var/tmp/exports/a', b'data')])
            Path(ref['path']).write_text('{}')
            with self.assertRaises(ValueError): updates.accessed('A', ref)

    def test_idle_session_receives_late_change_once_and_failed_dispatch_is_retryable(self):
        visible, _, _ = build_theory('continuation', 8, 'intended', publication_updates=True)
        reg = {'study_mode': 'swarmform-structure', 'workload': 'navier-stokes-theory',
               'population': 8, 'condition': 'intended', 'harness': {'goal_mode': 'off'},
               'deployment': {'kind': 'shared_files', 'shared': True},
               'publication_updates': policy(), 'budget': {'min_free_bytes': 1}}
        with tempfile.TemporaryDirectory() as directory:
            collection = StructureCollection(directory, reg, visible, api_key='offline')
            try:
                collection.publication_pool = Mock()
                collection.next_publication_scan = float('inf')
                for actor in collection.actors:
                    collection.agents[actor] = Mock()
                    collection.states[actor] = {'status': 'running', 'notices': [], 'session_activations': 1,
                                                'publication_notices': 0}
                    collection.active.add(actor)
                actor = 'Research02'
                contents = scan({'/var/tmp/exports/messages/late.json': envelope(actor)})
                collection.publications.observe(contents); collection.publications.observe(contents)
                collection.poll_publications()
                collection.agents[actor].prompt.assert_not_called()  # Still working.
                collection.handle(actor, {'type': 'settled', 'turn': 5, 'text': 'Initial contribution done.'}, None)
                self.assertEqual(collection.states[actor]['status'], 'idle')
                collection.agents[actor].prompt.side_effect = RuntimeError('dispatch failed')
                with self.assertRaises(RuntimeError): collection.poll_publications()
                self.assertTrue(collection.publications.pending(actor))
                collection.agents[actor].prompt.side_effect = None
                collection.poll_publications()
                self.assertEqual(collection.states[actor]['session_activations'], 2)
                self.assertIn(actor, collection.active)
                self.assertEqual(collection.publications.pending(actor), [])
                collection.handle(actor, {'type': 'settled', 'turn': 7, 'text': 'Reviewed.'}, None)
                collection.poll_publications()
                self.assertEqual(collection.states[actor]['session_activations'], 2)
                self.assertEqual(collection.states[actor]['publication_notices'], 1)
                # Empty time does not cause any prompt or bypass the quiet period.
                collection.active.clear()
                with patch('swarmform.structure_collection.time.monotonic', return_value=100):
                    self.assertFalse(collection.quiescence_ready())
                with patch('swarmform.structure_collection.time.monotonic', return_value=131):
                    self.assertTrue(collection.quiescence_ready())
                pending = Future(); collection.publication_scan = pending
                with patch('swarmform.structure_collection.time.monotonic', return_value=132):
                    self.assertFalse(collection.quiescence_ready())
                pending.set_exception(RuntimeError('scanner failed'))
                with self.assertRaises(RuntimeError): collection.poll_publications()
            finally:
                collection.pool.shutdown()


if __name__ == '__main__': unittest.main()
