"""Network-check admission without a Docker daemon or live model calls."""
from contextlib import contextmanager
import os
import select
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests import network_check_gate as gate


class NetworkCheckGateChecks(unittest.TestCase):
    def test_process_death_releases_lock_for_next_check(self):
        script = (
            'import sys; from tests.network_check_gate import serialized\n'
            'with serialized(sys.argv[1]):\n'
            ' print("acquired", flush=True); sys.stdin.read()\n'
        )
        with TemporaryDirectory() as directory:
            def start():
                return subprocess.Popen([sys.executable, '-c', script, directory],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)
            first = start()
            second = None
            try:
                self.assertTrue(select.select([first.stdout], [], [], 5)[0])
                self.assertEqual(first.stdout.readline().strip(), 'acquired')
                second = start()
                self.assertFalse(select.select([second.stdout], [], [], .25)[0])
                with self.assertRaisesRegex(TimeoutError, 'another networked preparation check'):
                    with gate.serialized(directory, timeout=.1):
                        self.fail('the first process still holds the lock')
                first.kill()
                first.wait(timeout=5)
                self.assertTrue(select.select([second.stdout], [], [], 5)[0])
                self.assertEqual(second.stdout.readline().strip(), 'acquired')
            finally:
                for proc in (first, second):
                    if proc is not None:
                        if proc.poll() is None:
                            proc.kill()
                        proc.communicate(timeout=5)

    def test_admission_waits_only_on_occupied_capacity(self):
        calls = []

        @contextmanager
        def reserve(count):
            calls.append(count)
            if len(calls) == 1:
                raise RuntimeError('Host capacity occupied: test')
            yield lambda pid: calls.append(pid)

        with patch.object(gate.launch_capacity, 'reserve', side_effect=reserve), \
                patch.object(gate.time, 'sleep'):
            gate.admit()
        self.assertEqual(calls, [4, 4, os.getpid()])

        @contextmanager
        def broken(_count):
            raise RuntimeError('daemon error')
            yield

        with patch.object(gate.launch_capacity, 'reserve', side_effect=broken):
            with self.assertRaisesRegex(RuntimeError, 'daemon error'):
                gate.admit()

        @contextmanager
        def occupied(_count):
            raise RuntimeError('Host capacity occupied: test')
            yield

        with patch.object(gate.launch_capacity, 'reserve', side_effect=occupied), \
                patch.object(gate.time, 'monotonic', side_effect=(0, 601)):
            with self.assertRaisesRegex(RuntimeError, 'Host capacity occupied'):
                gate.admit(timeout=600)

    def test_preparation_routes_direct_and_indirect_network_checks_to_gate(self):
        import run
        modules = tuple(sorted(run.NETWORK_CHECK_MODULES))
        for module in modules:
            self.assertTrue((run.HERE/'tests'/f'{module}_checks.py').is_file())
            command = run.preparation_check_command(run.HERE/'tests'/f'{module}_checks.py')
            self.assertEqual(command[-2:], ['tests.network_check_gate', f'tests.{module}_checks'])
        command = run.preparation_check_command(run.HERE/'tests'/'mechanism_review_checks.py')
        self.assertEqual(command[-3:], ['unittest', 'tests.mechanism_review_checks', '-v'])


if __name__ == '__main__':
    unittest.main()
