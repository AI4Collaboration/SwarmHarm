"""Offline checks for the explicit GLM model route; subject inputs stay unchanged."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def transport():
    spec = importlib.util.spec_from_file_location('glm_adapter_checks', HERE/'glm_transport.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class AdapterChecks(unittest.TestCase):
    def test_exact_model_only(self):
        t = transport()
        for name in ('deepseek-v4-pro', 'glm-any', 'gpt-6.1-sol'):
            with self.assertRaises(ValueError):
                t.configure(name, 'https://lmportal.iefbr14.xyz/v1')

    def test_host_only_key_and_exact_payload(self):
        t = transport()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'test-key'
            path.write_text('dummy-offline-credential')
            t.configure('glm-5.3-flash', 'https://lmportal.iefbr14.xyz/v1', key_file=path)
            payload = t.payload({'instructions': 'Complete the user\'s task.', 'reasoning': {'effort': 'high'}, 'input': []})
            self.assertEqual(payload['model'], 'glm-5.3-flash')
            self.assertEqual(payload['max_output_tokens'], 65536)
            self.assertEqual(t.ENDPOINT, 'https://lmportal.iefbr14.xyz/v1/responses')
            self.assertNotIn(t.key(), str(payload))
            self.assertFalse(payload['parallel_tool_calls'])

    def test_credentials_cannot_enter_endpoint(self):
        t = transport()
        for url in ('http://example.org/v1', 'https://user:pass@example.org/v1',
                    'https://example.org/v1?key=x', 'https://example.org/v1#x'):
            with self.assertRaises(ValueError):
                t.configure('glm-5.3-flash', url)


if __name__ == '__main__':
    unittest.main()
