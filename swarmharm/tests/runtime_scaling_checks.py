"""Population identity and real-network allocation contracts, without model calls."""
from ipaddress import ip_network
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
import json
import os
from threading import Lock
import time
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import reporting_cohort as cohort
import run
from phase2.terminal_batching import records_link as links


class RuntimeScalingChecks(unittest.TestCase):
    def test_startup_parallelism_does_not_cap_population(self):
        self.assertEqual(run.startup_workers(128, 128), 128)
        self.assertEqual(run.startup_workers(128, 8), 8)
        self.assertEqual(run.startup_workers(3, 128), 3)
        for invalid in (0, -1, 2.5, True):
            with self.assertRaisesRegex(ValueError, 'positive integer'):
                run.startup_workers(128, invalid)

    def test_128_distinct_actors_and_accounts(self):
        self.assertEqual(len(set(cohort.actor_ids(128))), 128)
        self.assertEqual(len(set(cohort.accounts(128))), 128)
        self.assertEqual(cohort.actor_ids(128)[-1], 'job-bose-4')

    def test_128_networks_skip_existing_ranges_and_wrap(self):
        def docker(*args, **kwargs):
            if args[:2] == ('network', 'ls'):
                return 'existing\n'
            return json.dumps([{'IPAM': {'Config': [{'Subnet': '10.240.0.0/24'}]}},
                               {'IPAM': {'Config': None}}])
        with patch.dict(os.environ, {'SWARMHARM_NETWORK_POOL': '10.240.0.0/22'}), \
                patch.object(links, 'docker', side_effect=docker), \
                patch.object(links.secrets, 'randbelow', return_value=127):
            subnets = list(islice(links.available_subnets(), 128))
        self.assertEqual(len(subnets), 96)  # 128 available /29s minus the occupied /24.
        self.assertEqual(len(set(subnets)), len(subnets))
        self.assertTrue(all(not ip_network(s).overlaps(ip_network('10.240.0.0/24')) for s in subnets))

    def test_concurrent_overlap_is_retried_without_reusing_a_link(self):
        created = []
        def docker(*args, **kwargs):
            if args[:2] == ('network', 'create'):
                subnet = args[args.index('--subnet') + 1]
                created.append(subnet)
                if len(created) == 1:
                    raise RuntimeError('Pool overlaps with other one on this address space')
            return ''
        with TemporaryDirectory() as directory, \
                patch.object(links, 'available_subnets', return_value=iter(
                    ('10.240.0.0/29', '10.240.0.8/29', '10.240.0.16/29'))), \
                patch.object(links, 'docker', side_effect=docker):
            link = links.RecordsLink(directory+'/service', 'fixture', {'owners': ['a', 'b']})
            self.assertEqual(len(link.networks), 2)
            link.close()
        self.assertEqual(created, ['10.240.0.0/29', '10.240.0.8/29', '10.240.0.16/29'])

    def test_128_observers_do_not_exhaust_server_processes(self):
        active = peak = 0
        counter = Lock()
        def docker(*args, **kwargs):
            nonlocal active, peak
            if args[0] != 'exec':
                return ''
            with counter:
                active += 1
                peak = max(peak, active)
            time.sleep(0.001)
            with counter:
                active -= 1
            return '{"sequence":1}\n'
        with TemporaryDirectory() as directory, \
                patch.object(links, 'available_subnets', return_value=iter(('10.240.0.0/29',))), \
                patch.object(links, 'docker', side_effect=docker):
            link = links.RecordsLink(directory+'/service', 'fixture', {'owners': ['a']})
            try:
                with ThreadPoolExecutor(max_workers=128) as pool:
                    results = list(pool.map(lambda _: link.journal(), range(128)))
                self.assertEqual(peak, 1)
                self.assertTrue(all(result == [{'sequence': 1}] for result in results))
            finally:
                link.close()


if __name__ == '__main__':
    unittest.main()
