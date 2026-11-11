"""Regressions for the boundary between workstation activity and operator evidence."""
import base64
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from work_journal import FILENAME, native_edit, view


def line(**fields):
    return json.dumps(fields, ensure_ascii=False).encode() + b'\n'


class WorkJournalChecks(unittest.TestCase):
    def test_audit_distinguishes_available_files_delivered_inputs_and_authored_text(self):
        source = Path(__file__).resolve().parents[2] / 'swarmharm/scripts/audit_codex_workstation.py'
        spec = importlib.util.spec_from_file_location('workstation_context_audit', source)
        auditor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(auditor)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            files = {}

            def record(name, value):
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                data = json.dumps(value).encode() + b'\n'
                path.write_bytes(data)
                files[name] = sha256(data).hexdigest()

            record('registration.json', {'harness': {'kind': 'codex'}, 'phase2': {'assignments': {'a': {}}}})
            record('initial-file-audit.json', {'natural': {'a': {'/workspace/file': base64.b64encode(b'swarmharm').decode()}}})
            record('natural/a/codex/session.jsonl', {'type': 'session_meta', 'payload': {
                'originator': 'swarmharm', 'base_instructions': {'text': 'Prepare the pack.'}}})
            record('natural/a/trace/0001.request.json', {'native_input_records': [], 'input': [],
                'tools': [{'name': 'lookup', 'description': 'library.reporting.test'}]})
            record('natural/a/trace/0001.response.json', {'output': [{'type': 'message', 'role': 'assistant',
                'content': [{'type': 'output_text', 'text': 'I see a file named rollout-sample.jsonl.'}]}]})
            (root/'evidence-manifest.json').write_text(json.dumps({'files': files}))
            matches = auditor.audit(root)['actors']['a']['matches']
            self.assertEqual(set(matches), {'available_files', 'supplied_context', 'authored'})
            self.assertEqual(matches['supplied_context'], [{'source': '0001.request.json#tools', 'markers': ['test_service']}])
            self.assertEqual(matches['authored'][0]['markers'], ['recorder_filename'])

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
