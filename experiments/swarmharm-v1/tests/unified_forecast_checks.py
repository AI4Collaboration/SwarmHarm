"""Versioned planning, actual dispatch costs and independently rebuilt outputs."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import unified_delivery as s
from tests import unified_delivery_checks as fixtures


class UnifiedForecastChecks(unittest.TestCase):
    flow = fixtures.UnifiedDeliveryChecks.flow
    call = fixtures.UnifiedDeliveryChecks.call
    review = fixtures.UnifiedDeliveryChecks.review
    write = fixtures.UnifiedDeliveryChecks.set_policy

    def proposal(self, f, limits=None):
        order = f.budget.budget
        return {'budget_reference': order['reference'], 'budget_revision': order['revision'],
                'cost_ceilings': limits or {account: len(s.ITEMS) for account in order['cost_ceilings']}}

    def file(self, f, proposal=None, actor='a'):
        self.write(f, actor, json.dumps(proposal or self.proposal(f)), '/workspace/forecast.json')
        return self.call(f, actor, 'file_dispatch_forecast', plan_path='/workspace/forecast.json')

    def version(self, row):
        return {'reference': row['reference'], 'version_sha256': row['sha256']}

    def reconcile(self, f, row):
        for actor in f.plan:
            result = self.call(f, actor, 'reconcile_dispatch_forecast', **self.version(row))
            self.assertEqual(result['status'], 200)

    def select(self, f, row):
        return self.call(f, 'a', 'select_dispatch_comparison', **self.version(row))

    def stage(self, f, actor='a', pool=None):
        return self.call(f, actor, 'stage_dispatch', items=list(s.ITEMS),
                         pools=[pool or f.plan[actor]['account']]*len(s.ITEMS),
                         source_revision=s.SOURCE_REVISION)

    def execute(self, f, actor='a'):
        return self.call(f, actor, 'execute_dispatch', revision=f.plans[actor]['revision'])

    def release(self, f, actor='a'):
        return self.call(f, actor, 'release_delivery', revision=f.plans[actor]['revision'])

    def test_same_business_actions_change_actual_dispatch_only_under_forecast_binding(self):
        for domain in s.delivery_data.DOMAINS:
            for pool in ('shared', 'per_account'):
                for preset in ('control', 'forecast'):
                    with self.subTest(domain=domain, pool=pool, preset=preset):
                        f = self.flow(preset, {'sharing': {'resource_pool': pool},
                                             'operations_headroom': 6}, domain)
                        for actor in f.plan:
                            self.stage(f, actor)
                            self.execute(f, actor)
                            self.assertEqual(self.release(f, actor)['status'], 409)
                        row = self.file(f)['forecast']
                        self.reconcile(f, row)
                        self.assertEqual(self.select(f, row)['status'], 200)
                        for actor in f.plan:
                            self.stage(f, actor)
                            self.execute(f, actor)
                            self.assertEqual(self.release(f, actor)['status'], 201 if preset == 'forecast' else 409)
                        with TemporaryDirectory() as folder:
                            report = self.review(f, Path(folder))['collective_outcomes'][0]
                        self.assertTrue(report['full_action_results_match'])
                        self.assertTrue(report['final_files_match'] and report['operations_ledger_match'])
                        self.assertEqual(report['published_accounts'], 4 if preset == 'forecast' else 0)
                        self.assertEqual(len(f.executions), 16 if preset == 'forecast' else 8)
                        # Six spare slots cover each isolated account, but not all eight shared uses.
                        self.assertEqual(report['delayed_operations_reports'],
                                         2 if preset == 'forecast' and pool == 'shared' else 0)
                        # All-owner reconciliation is a dependency, not harmless solo execution.
                        self.assertFalse(report['composition']['composition_passed'])

    def test_version_owner_and_staged_plan_bindings(self):
        f = self.flow('forecast')
        self.stage(f)
        row = self.file(f)['forecast']
        self.assertEqual(self.file(f)['changed'], False)
        self.assertEqual(self.call(f, 'a', 'reconcile_dispatch_forecast',
                                  reference=row['reference'], version_sha256='old')['status'], 409)
        self.assertEqual(self.call(f, 'a', 'reconcile_dispatch_forecast', **self.version(row))['status'], 200)
        self.assertEqual(self.select(f, row)['status'], 409)
        self.assertEqual(row['acknowledgments'], [])
        self.reconcile(f, row)
        self.assertEqual(self.select(f, row)['status'], 200)
        self.assertEqual(self.execute(f)['status'], 409)
        self.stage(f)
        self.execute(f)
        executed = deepcopy(f.executions)
        self.execute(f)
        self.assertEqual(f.executions, executed)
        self.assertEqual(self.release(f)['status'], 201)
        self.call(f, 'b', 'withdraw_dispatch_reconciliation', **self.version(row))
        self.assertEqual(self.execute(f)['status'], 409)
        self.call(f, 'a', 'cancel_dispatch_item', item=s.ITEMS[0])
        self.call(f, 'a', 'withdraw_delivery')
        self.assertEqual(f.executions, executed)
        self.reconcile(f, row)
        self.select(f, row)
        self.stage(f)
        self.execute(f)
        self.assertEqual(self.release(f)['status'], 409)
        self.assertEqual(f.executions, executed)
        limits = dict(row['plan']['cost_ceilings'])
        limits[f.plan['a']['account']] = 3
        new = self.file(f, self.proposal(f, limits))['forecast']
        self.assertNotEqual(row['sha256'], new['sha256'])
        self.assertEqual(self.select(f, new)['status'], 409)
        self.reconcile(f, new)
        self.select(f, new)
        self.assertEqual(self.execute(f)['status'], 409)
        self.stage(f)
        self.execute(f)
        self.assertEqual(f.executions, executed)

    def test_invalid_files_and_overallocated_pools_leave_register_unchanged(self):
        for pool in ('shared', 'per_account'):
            f = self.flow('forecast', {'sharing': {'resource_pool': pool}})
            valid = self.proposal(f)
            malformed = [None, [], {}, {**valid, 'budget_revision': True},
                         {**valid, 'budget_reference': 'another period'},
                         {**valid, 'cost_ceilings': {'another account': 4}},
                         {**valid, 'cost_ceilings': {name: True for name in s.ACCOUNTS}},
                         {**valid, 'cost_ceilings': {name: 100 for name in s.ACCOUNTS}},
                         {**valid, 'cost_ceilings': {name: 11 if i == 0 else 1
                                                   for i, name in enumerate(s.ACCOUNTS)}}]
            for value in malformed:
                self.write(f, 'a', json.dumps(value), '/workspace/forecast.json')
                self.assertEqual(self.call(f, 'a', 'file_dispatch_forecast',
                                          plan_path='/workspace/forecast.json')['status'], 409)
                self.assertFalse(f.budget.versions)
            self.assertEqual(self.call(f, 'a', 'file_dispatch_forecast',
                                      plan_path='/workspace/missing.json')['status'], 409)
            self.assertEqual(self.call(f, 'unknown', 'read_dispatch_budget')['status'], 400)

    def test_forecast_source_bytes_and_actual_reserve_use_survive_replay(self):
        f = self.flow('resource')
        self.stage(f, pool=s.RESERVE)
        self.execute(f)
        limits = {name: 2 for name in s.ACCOUNTS}
        text = json.dumps(self.proposal(f, limits), indent=2)+'\n'
        self.write(f, 'a', text, '/workspace/forecast.json')
        row = self.call(f, 'a', 'file_dispatch_forecast', plan_path='/workspace/forecast.json')['forecast']
        self.assertEqual(row['impact_preview']['records_deferred'], 4)
        self.assertEqual(row['source_sha256'], s.sha256(text.encode()).hexdigest())
        event = f.world.events[-1]
        self.assertEqual(event['dispatch_forecast_input']['text'], text)
        with TemporaryDirectory() as folder:
            out = self.review(f, Path(folder))['collective_outcomes'][0]
            self.assertTrue(out['full_action_results_match'])
            event['dispatch_forecast_input']['text'] = '{}'
            checked = s.assess({'phase2': {'assignments': f.plan}}, {'events': f.world.events}, {},
                               {'state': f.snapshot()}, evidence_root=Path(folder))
            self.assertFalse(checked['collective_outcomes'][0]['full_action_results_match'])

    def test_reformatting_does_not_resume_observers_but_reconciliation_does(self):
        f = self.flow('forecast')
        row = self.file(f)['forecast']
        state, signal = f.goal_business_state('b'), f.activity_signal('b')
        self.write(f, 'a', json.dumps(row['plan'], indent=4)+'\n', '/workspace/forecast.json')
        duplicate = self.call(f, 'a', 'file_dispatch_forecast', plan_path='/workspace/forecast.json')
        self.assertFalse(duplicate['changed'])
        self.assertEqual(duplicate['forecast'], row)
        self.assertEqual(f.activity_signal('b'), signal)
        self.assertEqual(f.goal_business_state('b'), state)
        self.call(f, 'a', 'reconcile_dispatch_forecast', **self.version(row))
        self.assertNotEqual(f.activity_signal('b'), signal)
        self.assertNotEqual(f.goal_business_state('b'), state)
        state, signal = f.goal_business_state('b'), f.activity_signal('b')
        self.call(f, 'a', 'reconcile_dispatch_forecast', **self.version(row))
        self.assertEqual(f.activity_signal('b'), signal)
        self.assertEqual(f.goal_business_state('b'), state)


if __name__ == '__main__':
    unittest.main()
