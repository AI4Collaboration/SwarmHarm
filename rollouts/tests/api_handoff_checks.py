"""Portable matrix integrity and non-destructive resume, without inference."""
import json
import gzip
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
        result = subprocess.run([sys.executable, str(ROOT/'rollouts/run_matrix.py'),
                                 '--model', 'local-test-model', '--harness', 'chat-completions', *args],
                                capture_output=True, text=True, check=True, cwd=ROOT)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_default_matrix_and_task_material_match_across_channels(self):
        rows = self.plan()
        self.assertEqual(len(rows), 72)
        self.assertEqual(list(dict.fromkeys(r['population'] for r in rows)), [4, 8, 16])
        self.assertEqual(sum(row['population'] for row in rows), 672)
        self.assertTrue(all(row['names'] == 'numbered' for row in rows))

    def test_finished_or_archived_attempts_are_not_restarted(self):
        import hashlib
        args = ['--tasks', 'service-plan', '--populations', '4']
        rows = self.plan(*args)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for i, row in enumerate(rows):
                suffix = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]
                out = root/'local-test-model'/'n4'/f"service-plan-{row['channel']}-r1-{suffix}"
                out.parent.mkdir(parents=True, exist_ok=True)
                if i == 0:
                    archive = out.with_suffix('.tar.gz')
                    archive.write_bytes(b'fixture')
                    out.with_name(out.name+'.archive.json').write_text(json.dumps(
                        {'archive': str(archive), 'sha256': 'fixture'}))
                else:
                    out.mkdir()
                    (out/'summary.json').write_text('{"complete": true, "physical_stop_verified": true}')
                    (out/'actor.jsonl.gz').write_bytes(gzip.compress(b'{}\n'))
                    (out/'evidence-manifest.json').write_text(json.dumps({
                        file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in out.iterdir()}))
            result = subprocess.run([sys.executable, str(ROOT/'rollouts/run_matrix.py'),
                                     '--model', 'local-test-model', '--harness', 'chat-completions', *args, '--execute', '--out', directory],
                                    capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(result.returncode, 0, result.stderr)
            index = json.loads((root/'index.json').read_text())
            self.assertEqual(len(index['runs']), 4)
            self.assertEqual(index['runs'][0]['status'], 'archived')
            self.assertFalse(list(root.rglob('*.log')))
            incompatible = subprocess.run([sys.executable, str(ROOT/'rollouts/run_matrix.py'),
                '--model', 'changed-model', '--harness', 'chat-completions', *args, '--execute', '--out', directory],
                capture_output=True, text=True, cwd=ROOT)
            self.assertNotEqual(incompatible.returncode, 0)
            self.assertIn('different plan', incompatible.stderr)


class NativeEventChecks(unittest.IsolatedAsyncioTestCase):
    async def test_partial_response_precedes_tool_and_usage_is_counted_once(self):
        with TemporaryDirectory() as directory:
            agent = Mock()
            cohort = SimpleNamespace(
                args=SimpleNamespace(harness='codex', model='openai/gpt-6.1-sol',
                    base_url='http://localhost/v1', _api_key='fixture',
                    api_protocol='chat-completions', served_model=None, seconds=30),
                out=Path(directory), stopping=threading.Event(), usage={}, errors={}, returns={},
                active_tools=set(), trace=Mock(), stop=Mock(), tool=Mock(return_value=({'output':'ok'}, None)),
                tool_completed=Mock(), visible={'tools':[], 'prompts':{'one':('task',)}})

            def create(kind, actor, events, **kwargs):
                call={'type':'function_call', 'name':'bash', 'call_id':'c1',
                      'arguments':json.dumps({'command':'pwd'})}
                kwargs['on_transport_response']({'model':'openai/gpt-6.1-sol',
                    'usage':{'total_tokens':15}})
                for message in [
                    {'type':'ready'},
                    {'type':'response_update', 'response':{'output':[call]}},
                    {'type':'tool_call', 'id':'reply', 'call_id':'c1|tool'},
                    {'type':'provider_response', 'event':{'response':{
                        'output':[call], 'usage':{'total_tokens':15}}}},
                    {'type':'settled', 'text':'done'},
                ]: events.put((actor, message))
                return agent

            with patch('swarmform.native_participant.model_session.create', side_effect=create):
                await participate(cohort, 'one', {'tokens':100, 'tools':10, 'responses':10})
            self.assertEqual(cohort.errors, {})
            self.assertEqual(cohort.usage['one'], {'responses':1, 'tools':1, 'tokens':15})
            cohort.tool.assert_called_once_with('one', 'pwd', 'c1')
            agent.reply.assert_called_once()
            agent.close.assert_called_once()
            self.assertEqual(cohort.returns, {'one':'model_finished'})


if __name__ == '__main__':
    unittest.main()
