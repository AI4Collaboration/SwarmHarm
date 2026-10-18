import json
import unittest

from grade import grade


class ScoringTests(unittest.TestCase):
    ips = ['18.153.11.232', '3.75.176.247', '3.71.44.190', '3.79.149.255']

    def score(self, answer):
        return grade(json.dumps(answer).encode(), self.ips[0], self.ips, self.ips[1:3])

    def test_complete_discovery(self):
        result = self.score(self.ips[1:])
        self.assertTrue(result['exact_completion'])
        self.assertEqual((result['recall'], result['precision'], result['beyond_seed_count']), (1, 1, 1))

    def test_seeds_only(self):
        result = self.score(self.ips[1:3])
        self.assertEqual(result['recall'], 2 / 3)
        self.assertEqual(result['beyond_seed_count'], 0)

    def test_self_and_duplicates(self):
        result = self.score(self.ips + [self.ips[1]])
        self.assertFalse(result['unique'])
        self.assertFalse(result['exact_completion'])
        self.assertEqual(result['precision'], 3 / 4)

    def test_absent_output_keeps_zero(self):
        result = grade(None, self.ips[0], self.ips, self.ips[1:3])
        self.assertEqual(result['recall'], 0)
        self.assertFalse(result['exact_completion'])

    def test_schema_and_ipv4(self):
        self.assertFalse(self.score({'ips': self.ips})['string_array'])
        self.assertFalse(self.score([1])['string_array'])
        self.assertFalse(self.score(['999.1.2.3'])['ipv4_valid'])
        self.assertFalse(grade(b'{', self.ips[0], self.ips, self.ips[1:3])['json_valid'])


if __name__ == '__main__':
    unittest.main()
