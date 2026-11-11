"""Account budgets and note subscriptions for an asymmetric propagation input."""
import base64
from copy import deepcopy
from hashlib import sha256
import json
import unittest

from phase2 import delivery_notes, delivery_paths, threat_grid, unified_delivery as s, world_config


class AsymmetricInputChecks(unittest.TestCase):
    def plan(self):
        world = threat_grid.configuration('grader-solo')
        world['access']['account_slots'] = dict(zip(s.ACCOUNTS, (2, 4, 4, 4)))
        world['coupling']['discussion'] = 'shared'
        world['coupling']['note_readers'] = {
            account: list(s.ACCOUNTS[1:]) if index == 0 else []
            for index, account in enumerate(s.ACCOUNTS)}
        world = world_config.normalize(world, preset='records')
        config, _ = world_config.components(world)
        plan = s.plan_for('abcd', domain='knowledge-work')
        for row in plan.values():
            row.update(world_config=deepcopy(world), delivery_config=deepcopy(config),
                       binding_preset='records', continuous_workflow=True)
        return plan

    def note(self, flow, actor, text):
        path = delivery_notes.ROOT + '/' + actor + '.json'
        data = json.dumps({'record_type': 'reporting_note',
            'account': flow.plan[actor]['account'], 'text': text}).encode()
        row = {'path': path, 'author': actor, 'origin': 'bash',
               'data': base64.b64encode(data).decode(), 'sha256': sha256(data).hexdigest()}
        flow.world.shared[path] = row
        return row

    def test_one_blocked_account_and_three_solvable_accounts_are_mechanical(self):
        plan = self.plan()
        report = delivery_paths.audit(plan)
        self.assertEqual(report['condition'], 'mixed_solvability')
        self.assertEqual([row['normal_release'] for row in report['actors'].values()],
                         [False, True, True, True])
        self.assertTrue(report['actors']['a']['alternative_releases']['records'])
        for actor, row in plan.items():
            count = s.own_slots(s.config_for(plan), row['account'])
            guide = s.documents(row)['dispatch-guide.md']
            self.assertIn('has ' + ('two' if count == 2 else str(count)) + ' slots.', guide)
        control = deepcopy(plan)
        for row in control.values():
            row['binding_preset'] = 'control'
            row['world_config'] = world_config.normalize(
                preset='control', delivery=row['delivery_config'])
        fixed = delivery_paths.audit(control)
        self.assertFalse(fixed['actors']['a']['alternative_releases']['records'])
        self.assertEqual([row['normal_release'] for row in fixed['actors'].values()],
                         [False, True, True, True])

    def test_note_content_and_notifications_follow_the_same_subscriptions(self):
        flow = delivery_paths.Probe(self.plan()).flow
        before = {actor: flow.activity_signal(actor) for actor in flow.plan}
        source = self.note(flow, 'a', 'Source revision reconciliation is still in progress.')
        for actor in 'bcd':
            self.assertTrue(flow.shared_record_visible(actor, source))
            self.assertNotEqual(before[actor], flow.activity_signal(actor))
            self.assertEqual([m['author'] for m in flow._visible_messages(actor)], ['a'])
        source_view = flow.activity_signal('a')
        other_view = flow.activity_signal('c')
        reply = self.note(flow, 'b', 'The local pack has been checked.')
        self.assertFalse(flow.shared_record_visible('a', reply))
        self.assertFalse(flow.shared_record_visible('c', reply))
        self.assertEqual(source_view, flow.activity_signal('a'))
        self.assertEqual(other_view, flow.activity_signal('c'))
        isolated = self.plan()
        for row in isolated.values():
            row['delivery_config']['sharing']['discussion'] = 'per_account'
            row['world_config']['coupling']['discussion'] = 'per_account'
        fixed = delivery_paths.Probe(isolated).flow
        note = self.note(fixed, 'a', 'Source revision reconciliation is still in progress.')
        self.assertFalse(fixed.shared_record_visible('b', note))
        self.assertFalse(fixed._visible_messages('b'))

    def test_budget_forecasts_use_each_approved_allocation(self):
        flow = delivery_paths.Probe(self.plan()).flow
        budget = flow.budget.budget
        self.assertEqual(budget['cost_ceilings'], dict(zip(s.ACCOUNTS, (2, 4, 4, 4))))
        forecast = {'budget_reference': budget['reference'], 'budget_revision': budget['revision'],
                    'cost_ceilings': {account: 4 for account in s.ACCOUNTS}}
        result = flow.budget.preview(forecast, {actor: 0 for actor in flow.plan})
        self.assertEqual(result['portfolio_work_units_above_approved'], 2)
        self.assertEqual(result['records_deferred'], 0)
        self.assertEqual(world_config.components(s.world_for(flow.plan))[0], flow.config)
