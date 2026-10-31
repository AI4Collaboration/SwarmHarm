"""Validate every maintained domain and channel through its business filing path."""

import unittest

from phase1 import cache_channels, channel_design, filing_controls, fixture_ids, schedule


class FullCacheFilingChecks(unittest.TestCase):
    def test_each_channel_enables_the_missing_filings_and_its_repair_blocks_them(self):
        for scenario in channel_design.DOMAINS:
            plan = schedule.compile_plan(scenario=scenario)[0]['natural']
            fixture_ids.register(plan)
            for kind in cache_channels.MECHANISMS:
                with self.subTest(scenario=scenario, kind=kind):
                    result = filing_controls.evaluate_pair(plan, kind)['branches']
                    self.assertEqual(result[f'cache_{kind}']['final_filed'], 8)
                    self.assertEqual(result[f'cache_{kind}_repaired']['final_filed'], 4)
