"""Counterfactual isolation witnesses through the real Phase 1 service dispatch."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from phase1 import cache_channels as cache, channel_design, fixture_ids, lab, schedule
import run
import review


def plan_for(scenario, profile):
    ids = iter(f'job-{i}' for i in range(4))
    plan = schedule.compile_plan(scenario=scenario, id_factory=ids.__next__)[0]['natural']
    for item in plan.values():
        item['phase1_channel_profile'] = profile
    return plan


def world_for(scenario, profile):
    plan = plan_for(scenario, profile)
    _, visibility = channel_design.compile_condition(profile, plan)
    return lab.World(plan, topology_spec=visibility)


class CacheChannelChecks(unittest.TestCase):
    def test_matched_archive_instance_reproduces_rows_and_default_stays_fresh(self):
        for scenario in channel_design.DOMAINS:
            first=plan_for(scenario,'cache_value');second=plan_for(scenario,'cache_value')
            fixture_ids.register(first,'ab'*16);fixture_ids.register(second,'ab'*16)
            self.assertEqual([lab.batch_for(v) for v in first.values()],
                             [lab.batch_for(v) for v in second.values()])
            self.assertEqual(fixture_ids.descriptor(first)['policy'],'operator_selected_matched_inputs')
            fixture_ids.register(second)
            self.assertEqual(fixture_ids.descriptor(second)['policy'],'fresh_per_registration')
            self.assertNotEqual(fixture_ids.descriptor(first)['namespace_sha256'],
                                fixture_ids.descriptor(second)['namespace_sha256'])
        for bad in ('x'*32,'ab'*15,23):
            with self.assertRaises(ValueError):fixture_ids.register(first,bad)

    def test_old_archive_handles_fail_and_current_locator_chain_works_in_four_domains(self):
        for scenario in channel_design.DOMAINS:
            with self.subTest(scenario=scenario):
                plan = plan_for(scenario, 'cache_count_repaired')
                legacy = {a: lab.batch_for(item) for a, item in plan.items()}
                fixture_ids.register(plan)
                previous = {a: lab.batch_for(item) for a, item in plan.items()}
                fixture_ids.register(plan)
                world = lab.World(plan)
                self.addCleanup(world.close)
                actors = list(plan)
                for index, actor in enumerate(actors):
                    successor = actors[(index + 1) % len(actors)]
                    own = lab.batch_for(plan[actor])['reviews'][1]
                    target = lab.batch_for(plan[successor])['reviews'][1]
                    for old in (legacy[actor]['reviews'][1], previous[actor]['reviews'][1]):
                        for field in ('record_id', 'index_id'):
                            self.assertEqual(world.call(actor, 1, 'fetch_archive',
                                                        {'record_id': old[field]})['status'], 404)
                        stale_query = old['retained_scope'] + ' ' + own['quote_name']
                        stale = world.call(actor, 2, 'search_archive', {'query': stale_query})
                        self.assertIn(stale['status'], (200, 422))
                        self.assertFalse(stale.get('matches'))
                    found = world.call(actor, 3, 'search_archive', {'query': own['quote_name']})
                    locator = world.call(actor, 4, 'fetch_archive',
                                         {'record_id': found['matches'][0]['record_id']})['record']
                    member = locator['member_locators'][0]
                    self.assertEqual(member['exact_lookup'], target['retained_scope'] + ' ' + target['quote_name'])
                    match = world.call(successor, 5, 'search_archive', {'query': member['exact_lookup']})
                    self.assertEqual(match['matches'][0]['record_id'], target['record_id'])
                    self.assertEqual(world.call(successor, 6, 'fetch_archive',
                                                {'record_id': target['record_id']})['status'], 200)

    def test_archive_namespace_is_operator_only_and_survives_source_publication(self):
        for scenario in ('engineering-capacity', 'knowledge-work'):
            plan = plan_for(scenario, 'cache_value')
            fixture_ids.register(plan)
            world = lab.World(plan)
            self.addCleanup(world.close)
            actor = next(iter(plan))
            item = plan[actor]
            nonce = item[fixture_ids.NONCE_FIELD]
            self.assertNotIn(nonce, json.dumps(lab.initial(plan, actor)))
            self.assertNotIn(nonce, ''.join(lab.DECODE(v) for v in lab.files(item, actor).values()))
            before = lab.batch_for(item)['reviews'][1]['record_id']
            self.assertTrue(world.publish_final_build())
            current = world.service(actor).batch['reviews'][1]['record_id']
            self.assertNotEqual(current, before)
            self.assertEqual(world.call(actor, 1, 'fetch_archive', {'record_id': before})['record']['record_status'], 'superseded')
            self.assertEqual(world.call(actor, 2, 'fetch_archive', {'record_id': current})['record']['record_status'], 'active')









    def test_invalid_inputs_do_not_mutate_state(self):
        world = world_for('data-analysis', 'cache_value')
        a = next(iter(world.plan))
        before = world.cache.snapshot()
        for name, args in [('cache_order', {'order': ['source'] * 3}),
                           ('cache_store', {'key': 'x', 'kind': 'invalid', 'content': 'x'}),
                           ('cache_read', {'key': 'x', 'job': 'foreign'}),
                           ('cache_store', {'key': 'x', 'kind': 'source', 'content': '字' * 16000})]:
            self.assertIn(world.call(a, 1, name, args)['status'], (400, 422))
        self.assertEqual(world.cache.snapshot(), before)




if __name__ == '__main__':
    unittest.main(verbosity=2)
