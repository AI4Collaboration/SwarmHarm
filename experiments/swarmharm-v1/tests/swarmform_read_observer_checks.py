"""Read evidence must contain returned bytes, not simply an open or a filename."""

import base64
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from swarmform.read_observer import observed_reads


def hexed(value):
    return ''.join('\\x'+format(v,'02x') for v in value.encode())


class ReadEvidenceChecks(unittest.TestCase):
    def test_only_complete_scalar_reads_supply_bytes(self):
        path = hexed('/var/tmp/exports/source.csv')
        content = hexed('units,37\n')
        valid = f'31  1794176304.123456 read(3<{path}>, "{content}", 4096) = 9'
        rows = observed_reads(valid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['path'], '/var/tmp/exports/source.csv')
        self.assertEqual(base64.b64decode(rows[0]['data_base64']), b'units,37\n')
        for nonread in (valid.replace(' = 9', ' = 300000'), valid.replace('read(', 'write('),
                        valid.replace(' = 9', ' = -1 EIO (Input/output error)'),
                        f'31  1794176304.123456 openat(AT_FDCWD, "{path}", O_RDONLY) = 3',
                        valid.replace('read(', 'readv('), valid.replace(f'<{path}>', '<'+hexed('/usr/lib/source.csv')+'>')):
            self.assertEqual(observed_reads(nonread), [])
        positioned = valid.replace('read(', 'pread64(').replace('4096)', '4096, 12)')
        self.assertEqual(observed_reads(positioned)[0]['explicit_offset'], 12)

    def test_real_background_read_and_private_observer_files(self):
        script = Path(__file__).resolve().parents[3] / 'scripts/check_swarmform_read_observer.py'
        with TemporaryDirectory() as folder:
            subprocess.run([sys.executable, str(script), '--output', str(Path(folder)/'observer')],
                           check=True, capture_output=True, timeout=120)


if __name__ == '__main__':
    unittest.main()
