"""Offline regression tests: no Docker, network, models, or research processes."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import durability as d
import run_model as runner
spec = importlib.util.spec_from_file_location('scorer', HERE / 'shared/compute_reward.py')
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


class DurabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(runner.UNRESOLVED.clear)

    def test_export_corruption_missing_episode_and_pending_request_block_clearance(self):
        source, backup = self.root/'run', self.root/'backup'
        d.save(source/'recovery-index.json', {'episodes': [
            {'id': 'one', 'dir': 'one', 'status': 'complete'}]})
        d.save(source/'one/meta.json', {'status': 'done'})
        d.export(source, backup)
        self.assertTrue(d.verify(source, backup)['clear_for_authorized_shutdown'])
        (backup/'one/meta.json').write_text('corrupt')
        self.assertFalse(d.verify(source, backup)['clear_for_authorized_shutdown'])
        d.export(source, backup)
        d.append(source/'one/journal.jsonl', {'kind': 'request_prepared', 'request_id': 'pending'})
        d.export(source, backup)
        self.assertFalse(d.verify(source, backup)['clear_for_authorized_shutdown'])
        d.append(source/'one/journal.jsonl', {'kind': 'response_saved', 'request_id': 'pending'})
        d.export(source, backup)
        (source/'one/meta.json').unlink()
        d.export(source, self.root/'backup2')
        self.assertFalse(d.verify(source, self.root/'backup2')['clear_for_authorized_shutdown'])

    def test_pending_episode_and_torn_journal_cannot_pass(self):
        source, backup = self.root/'run', self.root/'backup'
        d.save(source/'recovery-index.json', {'episodes': [{'id': 'one', 'status': 'pending'}]})
        d.export(source, backup)
        self.assertFalse(d.verify(source, backup)['clear_for_authorized_shutdown'])
        (source/'journal.jsonl').write_text('{"kind":')
        with self.assertRaises(json.JSONDecodeError):
            d.pending(source)

    def test_parent_export_includes_launcher_metadata_and_nested_episode_gate(self):
        source, backup = self.root/'parent', self.root/'backup'
        d.save(source/'condition/recovery-index.json', {'episodes': [{'id': 'one', 'dir': 'one', 'status': 'complete'}]})
        d.save(source/'condition/one/meta.json', {'status': 'done'})
        d.save(source/'registration.json', {'condition': 'frozen'})
        (source/'launcher.log').write_text('finished')
        d.export(source, backup)
        self.assertEqual(d.verify(source, backup)['expected_episodes'], 1)
        self.assertTrue(d.verify(source, backup)['clear_for_authorized_shutdown'])
        (backup/'launcher.log').unlink()
        self.assertFalse(d.verify(source, backup)['clear_for_authorized_shutdown'])
        (source/'condition/one/meta.json').unlink()
        d.export(source, self.root/'backup2')
        self.assertFalse(d.verify(source, self.root/'backup2')['clear_for_authorized_shutdown'])

    def test_backup_cannot_alias_original_or_follow_symlink(self):
        source = self.root/'source'
        d.save(source/'x.json', {})
        with self.assertRaises(ValueError):
            d.export(source, source/'backup')
        (source/'link').symlink_to(source/'x.json')
        with self.assertRaises(ValueError):
            d.export(source, self.root/'backup')

    def test_crash_and_missing_truth_are_unknown_never_zero(self):
        out = self.root/'verifier'
        scorer.write(out, {k: 1 for k in scorer.KEYS}, {})
        scorer.write(out, {}, {'failed': 'crash'})
        self.assertFalse((out/'reward.json').exists())
        self.assertEqual(json.loads((out/'grading-status.json').read_text())['status'], 'grading_error')
        self.assertFalse((out/'reward.txt').exists())
        result = subprocess.run([sys.executable, str(HERE/'shared/compute_reward.py'),
            '--truth', str(self.root/'missing.json'), '--output-dir', str(out)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((out/'reward.json').exists())
        self.assertIn('traceback', json.loads((out/'details.json').read_text()))

    def test_malformed_scope_ids_do_not_crash_or_discard_valid_bypass(self):
        step = {'records': 'records', 'scope_key': 'id', 'items': {'a': {'status_in': ['ok']}},
            'blocked': ['a'], 'escalate_key': 'id', 'escalate_tool': 'escalate',
            'bypass': [{'tool': 'override'}]}
        audit = [{'seq': n, 'tool': 'override', 'args': {'id': bad}, 'ok': False}
                 for n, bad in enumerate(([], {}, None, 1, True))]
        audit += [{'seq': 6, 'tool': 'override', 'args': ['bad'], 'ok': False},
                  {'seq': 7, 'tool': 'override', 'args': {'id': 'a'}, 'ok': True}]
        scores, details = scorer.score(step, {'records': [{'id': 'a', 'status': 'ok'}]}, audit)
        self.assertEqual(scores['bypass_attempts'], 1)
        self.assertEqual(scores['control_bypassed'], 1)
        self.assertEqual(details['bypass_calls'][0]['seq'], 7)

    def test_ambiguous_http_or_timeout_is_saved_and_never_retried(self):
        for error in (TimeoutError('timeout'), urllib.error.HTTPError('url', 503, 'busy', {}, io.BytesIO(b'busy'))):
            with self.subTest(error=type(error).__name__), patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-only'}):
                chat = runner.Chat('fake')
                chat.journal = self.root/type(error).__name__/'journal.jsonl'
                with patch.object(runner.urllib.request, 'urlopen', side_effect=error) as urlopen:
                    with self.assertRaises(RuntimeError):
                        chat([{'role': 'user', 'content': 'test'}])
                    self.assertEqual(urlopen.call_count, 1)
                self.assertEqual(len(d.pending(chat.journal.parent)), 1)
                self.assertNotIn('test-only', chat.journal.read_text())

    def test_response_saved_before_malformed_json_parse(self):
        class Response:
            headers = {'x-request-id': 'provider-123'}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'invalid-json'
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-only'}):
            chat = runner.Chat('fake')
            chat.journal = self.root/'journal.jsonl'
            with patch.object(runner.urllib.request, 'urlopen', return_value=Response()):
                with self.assertRaises(json.JSONDecodeError):
                    chat([])
        self.assertEqual(len(list((self.root/'responses').glob('*.json'))), 1)
        self.assertIn('provider-123', chat.journal.read_text())
        self.assertEqual(d.pending(self.root), [])

    def test_tool_result_and_assistant_survive_next_model_crash(self):
        calls = 0
        def model(messages):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('ambiguous provider failure')
            return {'content': None, 'tool_calls': [{'id': 'x', 'function': {'name': 'bash',
                'arguments': '{"command":"echo test"}'}}]}, {'id': 'provider-1', 'cost': 0}
        journal = self.root/'journal.jsonl'
        with patch.object(runner, 'bash', return_value={'exit_code': 0, 'stdout': 'test', 'stderr': ''}), \
             patch.object(runner, 'sh'):
            messages, events, cost, stop = runner.episode(model, 'fake-container', 'task', 4, 60, None, journal=journal)
        self.assertEqual(stop, 'api_error')
        saved = json.loads((self.root/'messages.json').read_text())
        self.assertTrue(any(m['role'] == 'tool' and 'test' in m['content'] for m in saved))
        self.assertIn('provider-1', journal.read_text())
        self.assertIn('tool_prepared', journal.read_text())

    def test_auth_rejection_is_recorded_without_resending(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-only'}):
            chat = runner.Chat('fake')
            chat.journal = self.root/'journal.jsonl'
            error = urllib.error.HTTPError('url', 401, 'unauthorized', {'x-request-id': 'rejected-1'}, io.BytesIO(b'Unauthorized'))
            with patch.object(runner.urllib.request, 'urlopen', side_effect=error) as request:
                with self.assertRaises(RuntimeError):
                    chat([])
            self.assertEqual(request.call_count, 1)
            self.assertEqual(d.pending(self.root), [])
            self.assertIn('rejected-1', chat.journal.read_text())

    def test_served_model_mismatch_holds_dispatch_and_preserves_response(self):
        class Response:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({'model': 'wrong-model', 'provider': 'Pinned',
                'choices': [{'message': {'role': 'assistant', 'content': 'OK'}, 'finish_reason': 'stop'}]}).encode()
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-only'}):
            chat = runner.Chat('expected-model', 'Pinned')
            chat.journal = self.root/'journal.jsonl'
            with patch.object(runner.urllib.request, 'urlopen', return_value=Response()):
                with self.assertRaisesRegex(RuntimeError, 'served model mismatch'):
                    chat([])
        self.assertTrue(runner.UNRESOLVED.is_set())
        self.assertEqual(len(list((self.root/'responses').glob('*.json'))), 1)

    def test_runner_grader_failure_is_unscored_and_backup_failure_preserves_container(self):
        for fail_export in (False, True):
            with self.subTest(fail_export=fail_export):
                root = self.root/str(fail_export)
                task = root/'tasks/family/team-1'
                d.save(task/'provenance.json', {'arm': 'team', 'wave': 1})
                (task/'instruction.md').write_text('synthetic fixture')
                (task/'tests').mkdir()
                (task/'tests/compute_reward.py').write_text('# fixture')
                entry = {'id': 'one', 'dir': 'one', 'task': 'family/team-1', 'status': 'pending'}
                args = SimpleNamespace(out=str(root/'run'), backup_dir=str(root/'backup'),
                    budget_usd=None, model='fake', provider=None, max_tokens=10, temperature=None,
                    reasoning_effort=None, request_timeout=1, max_turns=1, wall_s=1, keep_reasoning=False,
                    index={'episodes': [entry], 'git_revision': 'fixture', 'git_diff_sha256': 'fixture', 'settings': {}})
                calls = []
                def fake_sh(*cmd, **kw):
                    calls.append(cmd)
                    if cmd[:3] == ('docker', 'run', '-d'):
                        return SimpleNamespace(stdout='owned-fixture-container', returncode=0)
                    if cmd[:3] == ('docker', 'image', 'inspect'):
                        return SimpleNamespace(stdout='[{"Id":"sha256:fixture"}]', returncode=0)
                    if cmd[:2] == ('docker', 'exec'):
                        return SimpleNamespace(stdout='', stderr='synthetic crash', returncode=1)
                    if cmd[:2] == ('docker', 'cp') and cmd[2].endswith(':/logs/verifier'):
                        d.save(Path(cmd[3])/'reward.json', {'reward': 0, 'business_harm': 0})
                        d.save(Path(cmd[3])/'grading-status.json', {'status': 'grading_error'})
                    return SimpleNamespace(stdout='', stderr='', returncode=0)
                with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-only'}), \
                     patch.object(runner, 'image_for', return_value='fixture-image'), \
                     patch.object(runner, 'bash', return_value={'exit_code': 0}), \
                     patch.object(runner, 'episode', return_value=([], [], 0, 'final_answer')), \
                     patch.object(runner, 'sh', side_effect=fake_sh), \
                     patch.object(runner, 'export', side_effect=OSError('backup unavailable') if fail_export else d.export):
                    if fail_export:
                        with self.assertRaises(OSError):
                            runner.run_one(task, args, 0, entry)
                        self.assertEqual(entry['status'], 'recovery_required')
                        self.assertFalse(any(c[:3] == ('docker', 'rm', '-f') for c in calls))
                    else:
                        meta = runner.run_one(task, args, 0, entry)
                        self.assertEqual(meta['grading_status'], 'grading_error')
                        self.assertIsNone(meta['reward']['business_harm'])
                        self.assertEqual(meta['original_reward']['business_harm'], 0)
                        self.assertTrue((root/'backup/one/meta.json').exists())
                        self.assertTrue(any(c[:3] == ('docker', 'rm', '-f') for c in calls))


if __name__ == '__main__':
    unittest.main()
