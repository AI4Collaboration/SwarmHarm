"""Offline checks for the independently frozen DeepSeek transport port."""
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import run

class ReplicationChecks(unittest.TestCase):
    def test_existing_host_environment_needs_no_secret_file(self):
        with patch.object(run, 'API_KEY_ENV', 'OPENROUTER_API_KEY'), patch.dict(os.environ, {'OPENROUTER_API_KEY': 'dummy-test-value'}):
            self.assertIsNone(run.credential_path(None))
    def test_missing_environment_is_rejected_before_request(self):
        with patch.object(run, 'API_KEY_ENV', 'OPENROUTER_API_KEY'), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'unavailable'):run.credential_path(None)
    def test_unrelated_environment_is_not_a_credential(self):
        with patch.object(run, 'API_KEY_ENV', 'PATH'):
            with self.assertRaisesRegex(ValueError, 'Unsupported'):run.credential_path(None)
    def test_openrouter_endpoint_is_read_from_frozen_registration(self):
        self.assertEqual(run.registration_api_base({'api_base': 'https://openrouter.ai/api/v1'}), 'https://openrouter.ai/api/v1')
    def test_native_event_identity_is_saved_without_credentials(self):
        transport=run.module('replication_test_transport',run.REPO/'experiments/runtime/transport.py')
        transport.configure('test-model', 'https://openrouter.ai/api/v1', key_env='OPENROUTER_API_KEY', max_output_tokens=10)
        events=[{'type':'response.created','response':{'id':'request-test-id'}},{'type':'response.completed','response':{'id':'request-test-id','status':'completed','model':'test-model','output':[]}}]
        class Stream(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*_):self.close()
        encoded=b''.join(b'data: '+json.dumps(event).encode()+b'\n\n' for event in events)
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'OPENROUTER_API_KEY':'dummy-test-value'}), patch.object(transport.guardrails,'open_url',return_value=Stream(encoded)):
            transport.call({'model':'test-model','input':[]},temporary,'0001')
            text=(Path(temporary)/'0001.events.jsonl').read_text()
            self.assertEqual([json.loads(line) for line in text.splitlines()],events)
            self.assertNotIn('dummy-test-value',text)
if __name__=='__main__':unittest.main()
