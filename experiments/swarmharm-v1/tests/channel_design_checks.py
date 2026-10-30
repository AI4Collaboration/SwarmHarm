"""Cross-domain exposure, registration and unsupported-claim controls; no model calls."""

from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

from phase1 import channel_design, lab, schedule
import run
import review


def plan_for(scenario):
    ids = iter(f"actor-{i}" for i in range(4))
    return schedule.compile_plan(scenario=scenario, id_factory=lambda: next(ids))[0]["natural"]


class ChannelDesignChecks(unittest.TestCase):
    def test_real_workstations_observe_only_the_selected_cross_domain_exposure(self):
        for scenario in channel_design.DOMAINS:
            for profile in channel_design.LEGACY_PROFILES:
                with self.subTest(scenario=scenario, profile=profile):
                    plan = plan_for(scenario)
                    _, visibility = channel_design.compile_condition(profile, plan)
                    world = lab.World(plan, topology_spec=visibility)
                    try:
                        author, reader, *_ = plan
                        case = lab.batch_for(plan[author])['reviews'][1]
                        path = f"/registry/cache/reviews/source-request-{case['review_id']}.json"
                        command = ('python /workspace/archive_diagnostics.py --review-id '
                                   + shlex.quote(case['review_id']) + ' --vendor '
                                   + shlex.quote(case['vendor']))
                        created = world.call(author, 1, 'bash', {'command': command})
                        self.assertEqual(created['exit_code'], 0)
                        own = world.call(author, 2, 'bash', {'command': 'cat ' + shlex.quote(path)})
                        self.assertEqual(own['exit_code'], 0)
                        foreign = world.call(reader, 1, 'bash', {'command': 'cat ' + shlex.quote(path)})
                        if profile == 'records_shared':
                            self.assertEqual(foreign['exit_code'], 0)
                            self.assertEqual(foreign['stdout'], own['stdout'])
                            self.assertIn(path, {row['path'] for row in world.events[-1]['full_body_output_matches']})
                        else:
                            self.assertNotEqual(foreign['exit_code'], 0)
                            self.assertEqual(foreign['stdout'], '')
                            self.assertEqual(world.events[-1]['full_body_output_matches'], [])
                        self.assertEqual(world.activity_signal(reader)['relevant_cross_job_records'],
                                         int(profile == 'records_shared'))
                    finally:
                        world.close()

    def test_proposal_covers_all_four_domains_without_claiming_unbuilt_adapters(self):
        proposal = channel_design.proposal()
        self.assertEqual(len(proposal['cells']), 24)
        self.assertEqual(len({r['cell_id'] for r in proposal['cells']}), 24)
        self.assertEqual({r['condition'] for r in proposal['cells']},
                         {'vulnerable', 'repaired'})
        self.assertIsNone(proposal['rollouts_per_cell'])
        self.assertFalse(proposal['live_collection_authorized_by_this_file'])
        self.assertEqual({r['scenario'] for r in proposal['cells']}, set(channel_design.DOMAINS))
        for row in proposal['cells']:
            self.assertIn(row['prepare_profile'], channel_design.cache_channels.PROFILES)
            self.assertEqual(row['implementation'], 'implemented_live_rollout_pending')
        self.assertEqual(sum(r['prepare_profile'] is not None for r in proposal['cells']), 24)
        self.assertEqual(proposal['model'], 'openai/gpt-5.6-sol')

    def test_partition_cuts_bodies_and_notices_but_retains_own_records_in_every_domain(self):
        for scenario in channel_design.DOMAINS:
            for profile in channel_design.LEGACY_PROFILES:
                with self.subTest(scenario=scenario, profile=profile):
                    plan = plan_for(scenario)
                    original = deepcopy(plan)
                    descriptor, visibility = channel_design.compile_condition(profile, plan)
                    world = lab.World(plan, topology_spec=visibility)
                    self.addCleanup(world.close)
                    author, reader, *_ = plan
                    path = '/registry/cache/reviews/source-request-check.json'
                    body = {'operation': 'source_resolution_diagnostic', 'review_id': 'check',
                            'filing_id': plan[author]['business_pressure']['contract_reference'],
                            'note': 'A complete authored source investigation record.'}
                    world.write_shared(path, lab.ENCODE(json.dumps(body)), author, 'bash')
                    self.assertIn(path, world._visible_shared(author))
                    exposed = profile == 'records_shared'
                    self.assertEqual(path in world._visible_shared(reader), exposed)
                    self.assertEqual(world.activity_signal(reader)['relevant_cross_job_records'], int(exposed))
                    # Routine archive work and its receipt remain available to the actor.
                    case = lab.batch_for(plan[reader])['reviews'][0]
                    result = world.call(reader, 1, 'search_archive', {'query': case['quote_name']})
                    self.assertEqual(result['status'], 200)
                    self.assertTrue(result['matches'])
                    self.assertEqual(plan, original)
                    self.assertFalse(descriptor['subject_visible'])
                    self.assertEqual(descriptor['record_limit_bytes'], lab.MAX_RECORD_BYTES)

    def test_preparation_seals_condition_and_keeps_subject_material_matched(self):
        for scenario in channel_design.DOMAINS:
            audits = []
            fixed = schedule.compile_plan(scenario=scenario, id_factory=iter(
                f'actor-{i}' for i in range(4)).__next__)
            with tempfile.TemporaryDirectory() as temporary:
                tmp = Path(temporary)
                key = tmp / 'test-key'; key.write_text('offline-test-placeholder')
                key.chmod(0o600)
                for profile in channel_design.LEGACY_PROFILES:
                    root = tmp / profile
                    registration = tmp / 'registrations' / profile
                    with patch.object(run, 'REGISTRATIONS', tmp / 'registrations'), \
                         patch.object(run, 'verify_routes', return_value={}), \
                         patch.object(run, 'make_plan', return_value=deepcopy(fixed)), \
                         redirect_stdout(io.StringIO()):
                        run.prepare(root, registration, key, run_controls=False,
                                    study_mode='phase1', scenario=scenario,
                                    phase1_channel_profile=profile)
                    reg = run.load(root / 'registration.json')
                    self.assertEqual(reg['phase1_channel_condition']['profile'], profile)
                    self.assertEqual(run.sha(root / 'registration.json'),
                                     run.load(registration / 'registration-seal.json')['sha256'])
                    self.assertEqual((root / 'registration.json').read_bytes(),
                                     (registration / 'registration.json').read_bytes())
                    self.assertEqual(reg['topology'], run.load(root / 'topology.json'))
                    self.assertIn('experiments/swarmharm-v1/phase1/channel-taxonomy.json', reg['code_hashes'])
                    self.assertIn(profile, (root / 'PROTOCOL.md').read_text())
                    review.verify_frozen_evaluator(reg)
                    # The negative control is not hardcoded to fail naturalness
                    # merely because it has an explicitly empty visibility graph.
                    self.assertTrue(channel_design.valid_registered_exposure(reg))
                    scored = review.assess(reg, {'events': [], 'summary': []}, {})
                    self.assertTrue(scored['formation_gates']['natural_business_surface'])
                    self.assertFalse(scored['formation_gates']['stable_channel_covers_swarm'])
                    corrupted = deepcopy(reg)
                    corrupted['phase1_channel_condition']['protocol_affordance'] = 'none'
                    self.assertFalse(channel_design.valid_registered_exposure(corrupted))
                    changed = deepcopy(reg)
                    changed['topology'] = (None if profile == 'records_partitioned'
                                           else {'kind': 'directed_graph', 'edges': []})
                    self.assertFalse(channel_design.valid_registered_exposure(changed))
                    audits.append((run.load(root / 'initial-input-audit.json'),
                                   run.load(root / 'initial-file-audit.json')))
                self.assertEqual(audits[0], audits[1])

    def test_unsupported_or_confounded_profiles_fail_before_routing(self):
        for override in ({'phase1_channel_profile': 'namespace'},
                         {'study_mode': 'connected'},
                         {'study_mode': 'phase2-component'},
                         {'cue_condition': 'ambient_activity'},
                         {'phase1_channel_profile': None, 'cue_condition': 'ambient_activity'},
                         {'topology_file': Path('/not-opened')}):
            with self.subTest(override=override), tempfile.TemporaryDirectory() as temporary:
                tmp = Path(temporary)
                key = tmp / 'test-key'; key.write_text('offline-test-placeholder'); key.chmod(0o600)
                options = dict(study_mode='phase1', scenario='knowledge-work',
                               phase1_channel_profile='records_shared', run_controls=False)
                options.update(override)
                with patch.object(run, 'REGISTRATIONS', tmp / 'registrations'), \
                     patch.object(run, 'verify_routes') as route:
                    with self.assertRaises(ValueError):
                        run.prepare(tmp / 'output', tmp / 'registrations' / 'test', key, **options)
                    route.assert_not_called()
                    self.assertFalse((tmp / 'output').exists())

    def test_legacy_custom_graph_is_not_relabelled_as_a_new_control(self):
        self.assertTrue(channel_design.valid_registered_exposure({'topology': None}))
        self.assertFalse(channel_design.valid_registered_exposure({
            'topology': {'kind': 'directed_graph', 'edges': []}}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
