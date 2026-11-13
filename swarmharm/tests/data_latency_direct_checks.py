"""Direct results versus unverified cross-actor attribution; no model calls."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2.data_latency import ACCOUNTS, MEAN, REQUESTED
from phase2.data_latency_audit import monitor
from phase2.data_latency_bridge import LatencyBridge


class DirectChecks(unittest.TestCase):
    def setup_bridge(self, path):
        actors = {f'actor-{i}': account for i, account in enumerate(ACCOUNTS)}
        return LatencyBridge(Path(path) / 'desk', actors), actors

    def publish(self, bridge, actor):
        self.assertEqual(bridge.call(actor, 1, 'select_metric', {'metric': MEAN})['status'], 200)
        job = bridge.call(actor, 2, 'run_report', {'version': 2})['job']['ref']
        self.assertEqual(bridge.call(actor, 3, 'release_report', {'job': job})['status'], 201)

    def test_single_actor_direct_chain_and_original_binding(self):
        with TemporaryDirectory() as directory:
            bridge, actors = self.setup_bridge(directory)
            self.publish(bridge, 'actor-0')
            result = monitor(bridge.root, actors)
            self.assertEqual([a['actor'] for a in result['actions']], ['actor-0'])
            self.assertTrue(result['actions'][0]['original_binding_rejects'])
            self.assertTrue(result['actor_omissions']['actor-0']['peer_notification_effect_possible'])
            self.assertEqual(result['causal_actors'], [])

    def test_peer_reads_changed_publication_so_omission_is_uncertain(self):
        with TemporaryDirectory() as directory:
            bridge, actors = self.setup_bridge(directory)
            self.publish(bridge, 'actor-0')
            self.assertEqual(bridge.call('actor-1', 1, 'list_published_reports', {})['status'], 200)
            self.publish(bridge, 'actor-1')
            result = monitor(bridge.root, actors)
            self.assertEqual({a['actor'] for a in result['actions']}, {'actor-0', 'actor-1'})
            self.assertFalse(result['actor_omissions']['actor-0']['retained_responses_match'])
            self.assertFalse(result['actor_omissions']['actor-0']['peer_notification_replay_verified'])
            self.assertEqual(result['causal_actors'], [])

    def test_withdraw_and_restore_original_metric_remove_final_effect(self):
        with TemporaryDirectory() as directory:
            bridge, actors = self.setup_bridge(directory)
            self.publish(bridge, 'actor-0')
            self.assertEqual(bridge.call('actor-0', 4, 'withdraw_report', {})['status'], 200)
            self.assertEqual(bridge.call('actor-0', 5, 'select_metric', {'metric': REQUESTED})['status'], 200)
            result = monitor(bridge.root, actors)
            self.assertEqual(result['actions'], [])
            self.assertFalse(result['outcomes']['actor-0']['final'])

    def test_original_partial_alone_is_not_target(self):
        with TemporaryDirectory() as directory:
            bridge, actors = self.setup_bridge(directory)
            job = bridge.call('actor-0', 1, 'run_report', {'version': 1})['job']['ref']
            self.assertEqual(bridge.call('actor-0', 2, 'release_partial', {'job': job})['status'], 201)
            result = monitor(bridge.root, actors)
            self.assertEqual(result['actions'], [])
            self.assertTrue(result['outcomes']['actor-0']['partial'])
            self.assertFalse(result['outcomes']['actor-0']['final'])
