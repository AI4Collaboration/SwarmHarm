"""DeepSeek route, credential isolation and matched-input controls; zero network calls."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import deepseek
import deepseek_transport as transport
import run


class DeepSeekChecks(unittest.TestCase):
    def setUp(self):
        self.saved = (transport.MODEL, transport.ENDPOINT, transport.API_KEY_ENV, transport.API_KEY_FILE)
        transport.configure('deepseek-offline-test', 'https://api.deepseek.com', 'SWH_OFFLINE_KEY')
        self.body = {'instructions': "Complete the user's task.",
                     'input': [{'role': 'user', 'content': 'Check service availability.'}],
                     'tools': [], 'reasoning': {'effort': 'high'}}

    def tearDown(self):
        transport.MODEL, transport.ENDPOINT, transport.API_KEY_ENV, transport.API_KEY_FILE = self.saved

    def stream(self, response):
        return io.BytesIO(('data: ' + json.dumps({'type': 'response.completed', 'response': response}) + '\n').encode())

    def response(self, **changes):
        return {'model': transport.MODEL, 'status': 'completed',
                'output': [{'type': 'message', 'role': 'assistant',
                            'content': [{'type': 'output_text', 'text': 'Service available.'}]}], **changes}

    def test_missing_key_never_contacts_provider_or_uses_host_login(self):
        with patch.dict(os.environ, {}, clear=True), tempfile.TemporaryDirectory() as tmp, \
                patch.object(transport.urllib.request, 'urlopen') as request:
            with self.assertRaisesRegex(ValueError, 'No API credential'):
                transport.call(self.body, Path(tmp), '001')
            request.assert_not_called()
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_secret_is_only_an_authentication_header_not_a_study_artifact(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SWH_OFFLINE_KEY': 'offline-placeholder'}), \
                patch.object(transport.urllib.request, 'urlopen', return_value=self.stream(self.response())) as request:
            response = transport.call(self.body, Path(tmp), '001')
            self.assertEqual(transport.output_text(response), 'Service available.')
            actual = request.call_args.args[0]
            self.assertEqual(actual.get_header('Authorization'), 'Bearer offline-placeholder')
            self.assertEqual(json.loads(actual.data), json.loads((Path(tmp) / '001.request.json').read_text()))
            self.assertTrue(all('offline-placeholder' not in p.read_text() for p in Path(tmp).iterdir()))

    def test_returned_reasoning_and_tool_calls_are_retained_without_conversion(self):
        native = self.response(output=[{'type': 'reasoning', 'content': [{'type': 'reasoning_text', 'text': 'Offline fixture.'}]},
            {'type': 'function_call', 'name': 'confirm_service', 'call_id': 'call-test', 'arguments': '{}'}])
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SWH_OFFLINE_KEY': 'offline-placeholder'}), \
                patch.object(transport.urllib.request, 'urlopen', return_value=self.stream(native)):
            received = transport.call(self.body, Path(tmp), '001')
            self.assertEqual(received, native)
            following = deepcopy(self.body)
            following['input'] += received['output'] + [
                {'type': 'function_call_output', 'call_id': 'call-test', 'output': '{"status":"available"}'}]
            sent = transport.payload(following)
            self.assertEqual(sent['input'][1:3], native['output'])
            self.assertEqual(sent['instructions'], self.body['instructions'])

    def test_http_errors_are_recorded_once_without_retry(self):
        error = urllib.error.HTTPError('https://api.deepseek.com/responses', 503, 'Unavailable', {}, None)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SWH_OFFLINE_KEY': 'offline-placeholder'}), \
                patch.object(transport.urllib.request, 'urlopen', side_effect=error) as request:
            with self.assertRaisesRegex(RuntimeError, '503'):
                transport.call(self.body, Path(tmp), '001')
            self.assertEqual(request.call_count, 1)
            self.assertEqual(json.loads((Path(tmp) / '001.error.json').read_text()), {'http_status': 503})

    def test_timeout_is_preserved_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SWH_OFFLINE_KEY': 'offline-placeholder'}), \
                patch.object(transport.urllib.request, 'urlopen', side_effect=TimeoutError) as request:
            with self.assertRaises(TimeoutError):
                transport.call(self.body, Path(tmp), '001', timeout=2)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(json.loads((Path(tmp) / '001.error.json').read_text()), {'timeout_seconds': 2})

    def test_native_model_mismatch_is_not_relabelled_or_counted_as_success(self):
        response = self.response(model='different-model')
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SWH_OFFLINE_KEY': 'offline-placeholder'}), \
                patch.object(transport.urllib.request, 'urlopen', return_value=self.stream(response)):
            with self.assertRaisesRegex(RuntimeError, 'model mismatch'):
                transport.call(self.body, Path(tmp), '001')
            self.assertEqual(json.loads((Path(tmp) / '001.response.json').read_text())['model'], 'different-model')

    def test_provider_failure_reason_is_preserved_with_the_key_redacted(self):
        raw = {'error': {'type': 'upstream_error', 'message': 'At capacity; offline-placeholder'}}
        error = urllib.error.HTTPError('https://api.deepseek.com/responses', 503, 'Unavailable',
                                       {}, io.BytesIO(json.dumps(raw).encode()))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SWH_OFFLINE_KEY': 'offline-placeholder'}), \
                patch.object(transport.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaises(RuntimeError):
                transport.call(self.body, Path(tmp), '001')
            diagnostic = (Path(tmp) / '001.error.json').read_text()
            self.assertIn('At capacity', diagnostic)
            self.assertNotIn('offline-placeholder', diagnostic)

    def test_credential_bearing_or_insecure_endpoints_are_rejected(self):
        for url in ('http://api.deepseek.com', 'https://key@example.com', 'https://api.deepseek.com?token=x'):
            with self.assertRaises(ValueError):
                transport.configure('deepseek-offline-test', url)

    def test_preparation_matches_all_frozen_sol_inputs_and_preserves_fresh_worlds(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'SWH_OFFLINE_KEY': 'offline-placeholder'}), \
                patch.object(run, 'MODEL', run.MODEL), patch.object(run, 'EFFORT', run.EFFORT), \
                patch.object(run, 'transport', run.transport), patch.object(run, 'fixtures', run.fixtures), \
                patch.object(run, 'INPUT_REVISION', run.INPUT_REVISION):
            deepseek.configure('deepseek-offline-test', 'https://api.deepseek.com', 'SWH_OFFLINE_KEY')
            root = Path(tmp) / 'study'
            with redirect_stdout(io.StringIO()):
                deepseek.prepare(root)
            self.assertEqual(run.load(root / 'initial-input-audit.json'),
                             run.load(deepseek.REFERENCE / 'initial-input-audit.json'))
            actual, reference = run.load(root / 'registration.json'), run.load(deepseek.REFERENCE / 'registration.json')
            self.assertEqual(actual['worlds'], reference['worlds'])
            self.assertEqual(actual['budget'], reference['budget'])
            self.assertEqual(actual['pressure'], reference['pressure'])
            self.assertEqual(actual['model'], 'deepseek-offline-test')
            self.assertFalse((root / 'started.json').exists())
            self.assertTrue(all('offline-placeholder' not in p.read_text() for p in root.rglob('*.json')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
