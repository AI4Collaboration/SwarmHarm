"""Regressions for the boundary between workstation activity and operator evidence."""
import json
import unittest

from work_journal import FILENAME, native_edit, view


def line(**fields):
    return json.dumps(fields, ensure_ascii=False).encode() + b'\n'


class WorkJournalChecks(unittest.TestCase):
    def test_only_authored_work_and_tool_records_cross_the_boundary(self):
        for harness, hidden, public in (
            ('codex', line(type='response_item', payload={'type': 'message', 'role': 'developer'}),
             line(type='response_item', payload={'type': 'message', 'role': 'assistant', 'content': 'benchmark'})),
            ('claude', line(type='system', subtype='init', originator='operator'),
             line(type='user', uuid='one', message={'role': 'user', 'content': 'benchmark'})),
            ('pi', line(type='message', message={'role': 'system', 'content': 'operator setup'}),
             line(type='message', id='one', message={'role': 'toolResult', 'content': 'benchmark'})),
        ):
            with self.subTest(harness=harness):
                name = 'rollout-native-identity.jsonl'
                header = line(type='session_meta', originator='swarmharm')
                records = {name: header + hidden + public}
                visible = view(records)
                self.assertEqual(visible, {FILENAME: public})
                self.assertEqual(native_edit(records, visible, visible), records)
                self.assertEqual(native_edit(records, visible, {**visible, 'backup.jsonl': public}), records)
                self.assertEqual(native_edit(records, visible, {}), {name: header + hidden})
                with self.assertRaises(ValueError):
                    native_edit(records, visible, {FILENAME: header + public})
        with self.assertRaises(ValueError):
            view({'one.jsonl': b'', 'two.jsonl': b''})

    def test_edits_keep_native_headers_and_work_order(self):
        def message(text):
            return line(type='response_item', payload={'type': 'message', 'role': 'user', 'content': text})
        a, b, c, d = map(message, ('first', 'second', 'third', 'correction'))
        protected = line(type='world_state', state='operator only')
        name = 'rollout-source.jsonl'
        records = {name: protected + a + protected + b + protected + c}
        original = view(records)
        corrected = native_edit(records, original, {FILENAME: d + b + a})
        self.assertEqual(view(corrected), {FILENAME: d + b + a})
        self.assertEqual(corrected[name].count(protected), 3)
        restored = native_edit(corrected, view(corrected), original)
        self.assertEqual(view(restored), original)
        self.assertEqual(restored[name].count(protected), 3)
