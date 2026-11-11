"""Read evidence must contain returned bytes, not simply an open or a filename."""

import base64
import hashlib
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from swarmform.read_observer import ObservedFileStation, observed_reads


def hexed(value):
    return ''.join('\\x'+format(v,'02x') for v in value.encode())


class ReadEvidenceChecks(unittest.TestCase):
    def test_large_closed_trace_is_retained_without_container_memory_expansion(self):
        # A legitimate closed log fits the protected trace mount, but the former
        # base64/JSON capture exceeded the workstation's 512 MiB memory limit.
        with TemporaryDirectory() as folder:
            station = ObservedFileStation({}, archive=Path(folder)/'trace',
                                          process_lifecycle='continuous')
            def root_python(code):
                return subprocess.check_output(
                    ['docker', 'exec', '--user', '0:0', station.name,
                     'python', '-I', '-c', code], text=True, timeout=30)
            try:
                root_python("from pathlib import Path\n"
                            "with Path('/var/log/workstation/000001.log').open('wb') as f:\n"
                            " for i in range(110):f.write(bytes([i])*(1024*1024))\n"
                            " f.write(b'\\n')")
                expected = sha256()
                for i in range(110):
                    expected.update(bytes([i])*(1024*1024))
                expected.update(b'\n')
                memory = "from pathlib import Path;print(Path('/sys/fs/cgroup/memory.events').read_text())"
                before = root_python(memory)
                station.command_count = 1
                receipt = station.retain_traces()
                record = json.loads(Path(receipt['path']).read_text())
                log = record['files']['000001.log']
                self.assertEqual(log['bytes'], 110*1024*1024+1)
                self.assertEqual(log['sha256'], expected.hexdigest())
                with (station.archive/log['blob']).open('rb') as stream:
                    self.assertEqual(hashlib.file_digest(stream, 'sha256').hexdigest(), log['sha256'])
                self.assertIn('000001.log', station.pruned)
                self.assertEqual(root_python(memory), before)
                self.assertEqual(root_python("from pathlib import Path;print(list(Path('/var/log/workstation').iterdir()))").strip(), '[]')
                result, _ = station.execute('printf continued', {})
                self.assertEqual(result['stdout'], 'continued')
            finally:
                station.close()

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
        script = Path(__file__).resolve().parents[2] / 'swarmform/scripts/check_swarmform_read_observer.py'
        with TemporaryDirectory() as folder:
            subprocess.run([sys.executable, str(script), '--output', str(Path(folder)/'observer')],
                           check=True, capture_output=True, timeout=120)


if __name__ == '__main__':
    unittest.main()
