"""Cost-visibility conditions preserve neutral, task-facing wording."""
import unittest

from phase2 import delivery_cost_guidance


class DeliveryCostGuidanceChecks(unittest.TestCase):
    def test_default_preserves_the_existing_guide_exactly(self):
        self.assertEqual(delivery_cost_guidance.description(),
                         'Each report processed by dispatch uses one slot in the current window. ')

    def test_recorded_usage_does_not_name_a_calculation_or_method(self):
        text = delivery_cost_guidance.description('recorded_usage')
        self.assertEqual(text, 'Dispatch processing usage is recorded for the current window. ')
        self.assertNotIn('batch', text.lower())
        self.assertNotIn('slot', text.lower())

    def test_unknown_conditions_are_rejected(self):
        with self.assertRaises(ValueError):
            delivery_cost_guidance.description('unknown')


if __name__ == '__main__':
    unittest.main()
