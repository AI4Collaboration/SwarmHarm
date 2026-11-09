"""Worker-endpoint input coverage checks; no model calls or live services."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))

from check_swarmform_endpoint_inputs import ENCODINGS, catalog_check


class WorkerEndpointInputChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = catalog_check()

    def test_all_twenty_domain_encoding_inputs_are_runnable(self):
        self.assertEqual(len(self.rows), 20)
        self.assertEqual(len({(row['domain'], row['encoding']) for row in self.rows}), 20)
        self.assertEqual({row['encoding'] for row in self.rows}, set(ENCODINGS))
        self.assertTrue(all(row['runnable_registration']['kind'] == 'worker_endpoint'
                            for row in self.rows))

    def test_scope_and_encoding_do_not_change_worker_bytes(self):
        self.assertTrue(all(row['worker_bytes_equal_across_scope'] for row in self.rows))
        self.assertTrue(all(row['worker_bytes_equal_across_encodings'] for row in self.rows))
        self.assertEqual(len({row['shared_input_sha256'] for row in self.rows}), 20)
        self.assertTrue(all(row['shared_input_sha256'] != row['private_input_sha256']
                            for row in self.rows))

    def test_each_input_has_three_distinct_local_endpoints(self):
        for row in self.rows:
            with self.subTest(domain=row['domain'], encoding=row['encoding']):
                self.assertEqual(len(row['actors']), 3)
                self.assertEqual(len(set(row['endpoint_urls'].values())), 3)
                self.assertTrue(all(url.startswith('http://127.0.0.1:')
                                    for url in row['endpoint_urls'].values()))


if __name__ == '__main__':
    unittest.main()
