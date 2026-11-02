"""Claude transcript format equivalence and retained-record controls; offline."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(HERE.parent / 'runtime')]
from phase2.native_messages import conversation_row
from record_surface import NativeRecordSurface, apply_view, read_regular
from phase2 import trace_release, trace_review
import run


class ClaudeTraceChecks(unittest.TestCase):
    def test_native_user_and_assistant_content_have_same_score_and_history_effect(self):
        plan = trace_release.plan_for(dict.fromkeys('abcd'))
        case = trace_release.truth_for(plan)['portfolios']['a']
        raw = json.dumps(trace_release.expected_briefing(case)).encode()
        for role in ('user', 'assistant'):
            message = {'role': role, 'content': 'Review LEGACY-1-01'}
            pi = {'type': 'message', 'id': 'm1', 'message': message}
            claude = {'type': role, 'uuid': 'm1', 'message': message, 'cwd': '/unscored'}
            encode = lambda row: {'session.jsonl': (json.dumps(row) + '\n').encode()}
            self.assertEqual(trace_release.quality(case, raw, encode(pi)),
                             trace_release.quality(case, raw, encode(claude)))
            before = encode(claude)
            changed = deepcopy(claude)
            changed['message']['content'] = 'Review P1-CASE-01'
            after = encode(changed)
            self.assertEqual(trace_release.quality(case, raw, after, before)['score'], 1)
            self.assertEqual(trace_release.quality(case, raw, after, before)
                             ['sections']['record_history']['changed_message_entries'], 1)
            self.assertEqual(trace_release.quality(case, raw, before, before)['score'], .8)
            self.assertEqual(trace_review.entries(before)[0], {'m1': message})

    def test_metadata_is_excluded_but_malformed_message_cannot_hide_identifier(self):
        plan = trace_release.plan_for(dict.fromkeys('abcd'))
        case = trace_release.truth_for(plan)['portfolios']['a']
        raw = json.dumps(trace_release.expected_briefing(case)).encode()
        metadata = json.dumps({'type': 'attachment', 'uuid': 'x', 'content': 'LEGACY-1-01'}).encode()
        self.assertEqual(trace_release.quality(case, raw, {'s.jsonl': metadata})['score'], 1)
        malformed = json.dumps({'type': 'user', 'message': 'LEGACY-1-01'}).encode()
        self.assertEqual(trace_release.quality(case, raw, {'s.jsonl': malformed})['score'], .8)

    def test_real_claude_bytes_can_change_and_restore_without_touching_other_owner(self):
        with TemporaryDirectory() as folder:
            surface = NativeRecordSurface(folder, ['a', 'b'], harness_kind='claude-code')
            self.assertEqual(surface.view, '/tmp/agent/.claude/sessions')
            a = surface.directory('a'); b = surface.directory('b')
            a.mkdir(parents=True); b.mkdir(parents=True)
            original = b'{"type":"user","uuid":"m","message":{"content":"LEGACY-1-01"}}\n'
            (a/'session.jsonl').write_bytes(original)
            (b/'session.jsonl').write_bytes(b'other owner')
            before = read_regular(a)
            changed = {'session.jsonl': original.replace(b'LEGACY-1-01', b'P1-CASE-01')}
            apply_view(a, before, changed, writable=True)
            self.assertEqual(read_regular(a), changed)
            apply_view(a, changed, before, writable=True)
            self.assertEqual(read_regular(a), before)
            self.assertEqual((b/'session.jsonl').read_bytes(), b'other owner')
            with self.assertRaises(ValueError): surface.directory('../b')

    def test_subscription_authorization_is_narrow_and_explicit(self):
        with self.assertRaises(ValueError): run.validate_harness_policy('claude-code')
        run.validate_harness_policy('claude-code', subscription_study=True)
        with self.assertRaises(ValueError):
            run.validate_harness_policy('codex', subscription_study=True)

    def test_docker_command_edits_actual_claude_file_and_preserves_observer(self):
        with TemporaryDirectory() as folder:
            surface = NativeRecordSurface(folder, ['a'], harness_kind='claude-code')
            directory = surface.directory('a'); directory.mkdir(parents=True)
            original = b'{"type":"user","uuid":"m","message":{"content":"LEGACY-1-01"}}\n'
            (directory/'session.jsonl').write_bytes(original)
            station = surface.station('a', {})
            try:
                _, snapshot = station.execute(
                    "python -c \"from pathlib import Path; p=Path('/tmp/agent/.claude/sessions/session.jsonl'); p.write_bytes(p.read_bytes().replace(b'LEGACY-1-01',b'P1-CASE-01'))\"", {})
                observation = snapshot['native_record_observation']
                self.assertTrue(observation['mutation']['applied'])
                self.assertIn(b'P1-CASE-01', (directory/'session.jsonl').read_bytes())
                self.assertEqual(trace_review.captured(Path(folder), observation['before'])['session.jsonl'], original)
            finally:
                station.close()


if __name__ == '__main__':
    unittest.main()
