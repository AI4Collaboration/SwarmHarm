"""Read complete service snapshots even when their file index exceeds 64 MiB."""
import base64
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from swarmform.service_workstation import ServiceWorkstation


class ServiceCaptureChecks(unittest.TestCase):
    def capture(self, header, body, *, newline=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        station = ServiceWorkstation.__new__(ServiceWorkstation)
        station.service_archive = Path(temporary.name)
        station.service_capture_count = 0
        station.observation_sink = None
        station.name = 'capture-fixture'

        def write_capture(command, *, stdout, stderr, timeout):
            stdout.write(json.dumps(header).encode() + (b'\n' if newline else b'') + body)
            return SimpleNamespace(returncode=0)

        with patch('swarmform.service_workstation.subprocess.run', side_effect=write_capture):
            return station.capture_frozen('terminal'), station.service_archive

    def header(self):
        return {'bytes': 3, 'files': [
            {'root': '/workspace', 'path': '/workspace/report.txt', 'bytes': 3}]}

    def test_complete_index_above_previous_header_limit(self):
        header = self.header()
        # The Financial archive's real 253,637-entry index exceeded this limit.
        # Padding exercises the same serialized-header boundary without that many files.
        header['index_note'] = 'x' * (64 * 1024 * 1024)
        values, archive = self.capture(header, b'abc')
        self.assertEqual(values['/workspace']['/workspace/report.txt'], base64.b64encode(b'abc').decode())
        index = json.loads((archive / '000001.json').read_text())
        self.assertEqual(index['files']['/workspace/report.txt'], sha256(b'abc').hexdigest())
        with (archive / '000001.bin').open('rb') as stream:
            import hashlib
            self.assertEqual(index['raw_sha256'], hashlib.file_digest(stream, 'sha256').hexdigest())

    def test_truncated_body_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'capture is incomplete'):
            self.capture(self.header(), b'ab')

    def test_trailing_bytes_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'Unexpected bytes'):
            self.capture(self.header(), b'abcd')

    def test_unterminated_header_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'header is incomplete'):
            self.capture(self.header(), b'', newline=False)


if __name__ == '__main__':
    unittest.main()
