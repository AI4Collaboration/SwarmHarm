"""Customer checkpoints never fabricate dialogue or repeat a delivered notice."""
import unittest
from customer_updates import CHECKPOINTS, CustomerUpdates


class CustomerUpdateChecks(unittest.TestCase):
    def test_due_once_and_in_order_after_activation(self):
        updates = CustomerUpdates(['a', 'b'], CHECKPOINTS)
        self.assertFalse(updates.pending(lambda _: False))
        self.assertIsNone(updates.due('a', 999))
        updates.start(100)
        self.assertIsNone(updates.due('a', 129))
        self.assertEqual(updates.due('a', 130)[0], 0)
        updates.delivered('a', 0)
        self.assertIsNone(updates.due('a', 131))
        self.assertEqual(updates.due('b', 131)[0], 0)
        with self.assertRaises(ValueError):
            updates.delivered('a', 0)
        self.assertEqual(updates.due('a', 190)[0], 1)

    def test_safe_incomplete_work_gets_finite_updates_and_complete_work_can_finish(self):
        updates = CustomerUpdates(['a'], CHECKPOINTS)
        updates.start(0)
        self.assertFalse(updates.pending(lambda _: True))
        for index in range(3):
            self.assertTrue(updates.pending(lambda _: False))
            self.assertEqual(updates.due('a', 1000)[0], index)
            updates.delivered('a', index)
        self.assertFalse(updates.pending(lambda _: False))
        self.assertIsNone(updates.due('a', 2000))

    def test_default_is_no_added_updates(self):
        updates = CustomerUpdates(['a'])
        updates.start(0)
        self.assertFalse(updates.pending(lambda _: False))
        self.assertIsNone(updates.due('a', 1000))
