"""Delivery timing is separate from the registered payment-loss verdict."""
import unittest
from scripts.review_finance_timeliness import timing

class TimelinessChecks(unittest.TestCase):
    def test_deadline_and_invalid_order(self):
        start = '2026-11-12T14:00:00+00:00'
        self.assertTrue(timing(start, 300, '2026-11-12T14:05:00+00:00')['on_time'])
        late = timing(start, 300, '2026-11-12T14:05:00.001+00:00')
        self.assertFalse(late['on_time'])
        self.assertEqual(late['late_seconds'], .001)
        with self.assertRaises(ValueError):
            timing(start, 300, '2026-11-12T13:59:59+00:00')
        with self.assertRaises(ValueError):
            timing('2026-11-12T14:00:00', 300, '2026-11-12T14:05:00+00:00')
