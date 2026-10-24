import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import run
from durability import save
from launch import configuration
from recover import held_stage


class ResumeTests(unittest.TestCase):
    def checkpoint(self, root):
        agent = root / 'agents/solo'; agent.mkdir(parents=True)
        order = run.instruction(0, 1, 'solo')
        messages = [{'role': 'system', 'content': run.SYSTEM}, {'role': 'user', 'content': order}]
        assistant = {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'tool-1', 'type': 'function', 'function': {'name': 'bash', 'arguments': '{"command":"office ledger"}'}}]}
        result = {'exit_code': 0, 'stdout': '[]', 'stderr': ''}
        events = [{'kind': 'episode_started', 'messages': messages[:1]},
                  {'kind': 'user_added', 'message': messages[-1], 'wave': 1, 'stage': 0},
                  {'kind': 'request_prepared', 'request_id': 'r1', 'body': {'messages': list(messages)}, 'time': time.time() - 10},
                  {'kind': 'response_saved', 'request_id': 'r1'},
                  {'kind': 'assistant_response', 'message': assistant, 'metadata': {'usage': {'completion_tokens': 20}}},
                  {'kind': 'assistant_kept'}, {'kind': 'tool_prepared', 'call': assistant['tool_calls'][0]},
                  {'kind': 'tool_result', 'call_id': 'tool-1', 'result': result},
                  {'kind': 'stage_ended', 'stop': 'unresolved_request_hold'}]
        messages += [assistant, {'role': 'tool', 'tool_call_id': 'tool-1', 'content': json.dumps(result)}]
        save(agent / 'messages.json', messages)
        save(root / 'meta.json', {'stages': [{'wave': 1, 'stage': 0, 'agent': 'solo', 'stop': 'unresolved_request_hold'}]})
        (agent / 'journal.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
        return agent, events, messages

    def test_only_next_request_and_original_quotas_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); agent, _, messages = self.checkpoint(root)
            _, history, budget = held_stage(root)
            self.assertEqual(history, messages)
            self.assertEqual(budget['stage_calls_remaining'], 39)
            self.assertEqual(budget['calls_remaining'], 119)
            self.assertEqual(budget['remaining'], 131052)
            self.assertLess(budget['remaining_seconds'], 7200)
            class Model:
                body = {}
                def __call__(self, received):
                    self.seen = list(received)
                    return {'role': 'assistant', 'content': 'Done'}, {'usage': {'completion_tokens': 1}, 'finish_reason': 'stop'}
            model = Model(); run.native.UNRESOLVED.clear()
            stop = run.stage(model, 'unused', history, 'unused', agent, 'solo', 1, 0, budget, resume=True)
            self.assertEqual(stop, 'final_answer')
            self.assertEqual(model.seen, messages)
            events = [json.loads(l) for l in (agent / 'journal.jsonl').read_text().splitlines()]
            self.assertEqual(sum(e['kind'] == 'user_added' for e in events), 1)

    def test_unknown_request_blocks_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); agent, events, _ = self.checkpoint(root)
            (agent / 'journal.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events if e['kind'] != 'response_saved'))
            with self.assertRaisesRegex(ValueError, 'Unknown request'): held_stage(root)

    def test_unfinished_tool_blocks_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); agent, events, _ = self.checkpoint(root)
            (agent / 'journal.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events if e['kind'] != 'tool_result'))
            with self.assertRaisesRegex(ValueError, 'Unfinished tool'): held_stage(root)

    def test_inconsistent_history_blocks_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); agent, _, messages = self.checkpoint(root)
            save(agent / 'messages.json', messages[:-1])
            with self.assertRaisesRegex(ValueError, 'fully committed'): held_stage(root)

    def test_launchd_definition_never_keeps_failed_job_alive(self):
        job = configuration('test.job', ['/usr/bin/python3', 'supervise.py'], Path('/tmp'))
        self.assertIs(job['KeepAlive'], False)
        self.assertIs(job['RunAtLoad'], True)

    def test_resume_does_not_reset_stage_cap(self):
        class Model:
            body = {}; calls = 0
            def __call__(self, messages):
                self.calls += 1
                return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'last-call',
                    'function': {'name': 'bash', 'arguments': '{"command":"office ledger"}'}}]}, {
                    'usage': {'completion_tokens': 1}, 'finish_reason': 'tool_calls'}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); agent, _, messages = self.checkpoint(root)
            model = Model(); run.native.UNRESOLVED.clear(); run.BACKUP = root / 'backup'; run.CURRENT.campaign = 'test'
            with patch.object(run, 'read_state', return_value={'audit': []}), patch.object(run, 'snapshot', return_value={'audit': []}), \
                 patch.object(run.native, 'bash', return_value={'exit_code': 0, 'stdout': '[]', 'stderr': ''}), patch.object(run, 'export'):
                stop = run.stage(model, 'unused', messages, 'unused', agent, 'solo', 1, 0,
                                 {'remaining': 10000, 'calls_remaining': 50, 'stage_calls_remaining': 1}, resume=True)
            self.assertEqual(stop, 'max_turns')
            self.assertEqual(model.calls, 1)

    def test_wave_deadline_prevents_late_tool_dispatch(self):
        budget = {'remaining': 10000, 'calls_remaining': 120, 'deadline': time.monotonic() + 100}
        class Model:
            body = {}
            def __call__(self, messages):
                budget['deadline'] = time.monotonic() - 1
                return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'too-late',
                    'function': {'name': 'bash', 'arguments': '{"command":"office post --item A-104 --cents 1"}'}}]}, {
                    'usage': {'completion_tokens': 1}, 'finish_reason': 'tool_calls'}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); agent, _, messages = self.checkpoint(root)
            run.native.UNRESOLVED.clear()
            with patch.object(run.native, 'bash') as bash:
                stop = run.stage(Model(), 'unused', messages, 'unused', agent, 'solo', 1, 0, budget, resume=True)
            self.assertEqual(stop, 'wall_clock')
            bash.assert_not_called()


if __name__ == '__main__': unittest.main()
