"""Host launch admission, without a model or Docker daemon."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import launch_capacity as capacity


class HostCapacityChecks(unittest.TestCase):
    def test_removed_network_during_inspection_keeps_surviving_occupancy(self):
        result = subprocess.CompletedProcess(['docker', 'network', 'inspect'], 1,
            '[{"Labels":{"org.swarmharm.owner-pid":"100"}}]',
            'Error response from daemon: network retired not found\n')
        with patch.object(capacity.subprocess, 'check_output', return_value='live\nretired\n'), \
                patch.object(capacity.subprocess, 'run', return_value=result):
            self.assertEqual(capacity.managed_networks(), Counter({'100': 1}))

    def test_daemon_failure_is_not_free_capacity(self):
        result = subprocess.CompletedProcess(['docker', 'network', 'inspect'], 1,
                                            '[]', 'Cannot connect to the Docker daemon\n')
        with patch.object(capacity.subprocess, 'check_output', return_value='live\n'), \
                patch.object(capacity.subprocess, 'run', return_value=result):
            with self.assertRaises(subprocess.CalledProcessError):
                capacity.managed_networks()

    def test_simultaneous_launches_reserve_before_network_creation(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(capacity, 'managed_networks', return_value=Counter()), \
                patch.object(capacity, 'process_alive', return_value=True), \
                patch.dict(capacity.os.environ, {'SWARMHARM_MAX_WORKSTATION_NETWORKS': '16'}):
            def start(pid):
                try:
                    with capacity.reserve(4, directory=temp) as register:
                        register(pid)
                    return True
                except RuntimeError:
                    return False
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(start, range(100, 108))), 4)
            self.assertEqual(sum(json.loads((Path(temp)/'reservations.json').read_text()).values()), 16)

    def test_actual_networks_and_pending_reservations_are_not_double_counted(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(capacity, 'managed_networks', return_value=Counter({'100': 4})), \
                patch.object(capacity, 'process_alive', return_value=True), \
                patch.dict(capacity.os.environ, {'SWARMHARM_MAX_WORKSTATION_NETWORKS': '8'}):
            (Path(temp)/'reservations.json').write_text('{"100":4}')
            with capacity.reserve(4, directory=temp) as register:
                register(101)
            with self.assertRaisesRegex(RuntimeError, 'No model request'):
                with capacity.reserve(1, directory=temp):
                    self.fail('capacity should be full')

    def test_exited_reservation_releases_capacity_but_retained_networks_still_count(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(capacity, 'managed_networks', return_value=Counter({'100': 4})), \
                patch.object(capacity, 'process_alive', return_value=False), \
                patch.dict(capacity.os.environ, {'SWARMHARM_MAX_WORKSTATION_NETWORKS': '8'}):
            (Path(temp)/'reservations.json').write_text('{"100":8}')
            with capacity.reserve(4, directory=temp) as register:
                register(101)
            self.assertEqual(json.loads((Path(temp)/'reservations.json').read_text()), {'101': 4})
            with self.assertRaises(RuntimeError):
                with capacity.reserve(5, directory=temp):
                    self.fail('retained networks should count')

    def test_cannot_reserve_invalid_network_counts(self):
        self.assertGreaterEqual(capacity.DEFAULT_NETWORK_LIMIT, 32)
        with self.assertRaises(ValueError):
            with capacity.reserve(0):
                pass
        with patch.dict(capacity.os.environ, {'SWARMHARM_MAX_WORKSTATION_NETWORKS': '0'}):
            with self.assertRaises(ValueError):
                with capacity.reserve(4):
                    pass


if __name__ == '__main__':
    unittest.main()
