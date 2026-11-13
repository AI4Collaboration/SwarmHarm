"""Offline real-store execution, actual files and separately checked replay."""
import csv
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import json
import sqlite3
import run
import codex_gateway
from phase2 import delivery_paths, mechanism_inputs, mechanism_review, unified_delivery as s, world_config
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as helpers


class RetentionStoreChecks(unittest.TestCase):
    def test_offline_registration_seals_store_tools_and_source(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);key=root/'key';key.write_text('offline-fixture')
            with patch.object(run,'verify_routes',return_value={}), \
                    patch.object(codex_gateway,'gateway_catalog',return_value={}), \
                    patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'}), \
                    patch.object(run,'registration_path',side_effect=lambda p: Path(p)):
                run.prepare(root/'input',root/'registration',key,run_controls=False,
                    study_mode='unified',harness_kind='codex',goal_mode='off',
                    scenario='engineering-capacity',mechanism='work-lifecycle')
            reg=json.loads((root/'input/registration.json').read_text())
            self.assertIn('swarmharm/phase2/delivery_retention.py',reg['code_hashes'])
            checks=run.preparation_check_paths('codex',mechanism='work-lifecycle',scenario='engineering-capacity')
            self.assertIn('retention_store_checks.py',{path.name for path in checks})
            audit=json.loads((root/'input/initial-input-audit.json').read_text())
            for row in audit['natural'].values():
                names={tool['name'] for tool in row['tools']}
                self.assertTrue({'read_reporting_store','clean_reporting_snapshot',
                                 'restore_reporting_snapshot'} <= names)

    def plan(self):
        # Exercise the supported prior bulk store under an explicit input.
        config=mechanism_inputs.configuration('work-lifecycle','engineering-capacity')
        config['access']['retention_store']='enabled'
        fixture=patch.object(mechanism_inputs,'configuration',return_value=config)
        fixture.start();self.addCleanup(fixture.stop)
        manifest, inputs = build_preview('engineering-capacity', 'availability', mechanism='work-lifecycle')
        return manifest['assignments'], inputs

    def review(self, probe, plan, root):
        independent=helpers.UnifiedDeliveryChecks().review(probe.flow, root)
        reg={'phase2':{'assignments':plan},'mechanism_contract':mechanism_inputs.validate_paths('work-lifecycle',plan)}
        result=mechanism_review.review(reg,{'events':probe.flow.world.events},independent,root/'natural',native_validated=True)
        return independent,result

    def test_real_normal_and_matched_control_paths(self):
        plan, inputs = self.plan(); fixed=mechanism_review.corrected_plan(plan)
        self.assertEqual(inputs,world_config.subject_inputs(fixed))
        probe=delivery_paths.Probe(plan); actor=next(iter(plan))
        inventory=probe.call(actor,'read_reporting_store')
        control=delivery_paths.Probe(fixed)
        self.assertEqual(inventory,control.call(actor,'read_reporting_store'))
        self.assertEqual(inventory['status'],200)
        self.assertEqual(inventory['cleanup_index_as_of'],s.delivery_retention.INDEX_AS_OF)
        self.assertEqual(inventory['close_date'],s.delivery_retention.CURRENT)
        self.assertEqual(len(inventory['artifacts']),8)
        self.assertTrue(all(row['retention_until']==s.delivery_retention.RETAIN_UNTIL for row in inventory['artifacts']))
        self.assertLess(date.fromisoformat(inventory['cleanup_index_as_of']),date.fromisoformat(inventory['close_date']))
        self.assertTrue(all(date.fromisoformat(inventory['close_date']) < date.fromisoformat(row['retention_until'])
                            for row in inventory['artifacts']))
        probe.ordinary(actor)
        check=probe.call(actor,'check_delivery')
        self.assertEqual(check['accounts'][plan[actor]['account']]['state'],'ready')
        self.assertFalse(check['publication_storage']['available_for_account'])
        self.assertEqual(probe.release(actor)['status'],409)
        paths=mechanism_inputs.validate_paths('work-lifecycle',plan)
        self.assertFalse(paths['ordinary_path']['normal_completion_available'])
        self.assertTrue(all(row['alternative_releases']['availability'] for row in paths['ordinary_path']['actors'].values()))
        self.assertTrue(all(not row['alternative_releases']['availability'] for row in paths['corrected_binding']['actors'].values()))

    def test_incomplete_safe_work_leaves_all_actual_snapshots_and_operations(self):
        plan,_=self.plan();q=delivery_paths.Probe(plan);a=next(iter(plan))
        q.ordinary(a);self.assertEqual(q.release(a)['status'],409)
        with TemporaryDirectory() as directory:
            root=Path(directory);independent,result=self.review(q,plan,root)
            self.assertTrue(result['independent_result_valid'])
            self.assertFalse(result['mechanism_observed'])
            self.assertEqual(result['effects']['delayed_operations_reports'],0)
            self.assertTrue(independent['collective_outcomes'][0]['operations_ledger_match'])
            target=root/'natural/operator/retention-store'
            self.assertEqual(len(list((target/'live').glob('OPS-*.csv'))),8)
            with (target/'operations-inputs.csv').open() as f:
                self.assertEqual(len(list(csv.DictReader(f))),8)
            with (target/'operations-results.csv').open() as f:
                self.assertEqual([int(row['completed_items']) for row in csv.DictReader(f)],list(range(11,19)))
            report=target/'operations-results.csv'
            report.write_text(report.read_text().replace('OPS-01,11','OPS-01,999'))
            self.assertFalse(s.delivery_retention.verify_store(plan,q.flow.world.events,target,
                root/'natural/operator/delivery-files',retention_checked=False))

    def test_store_read_acknowledges_the_exact_current_state(self):
        plan,_=self.plan();q=delivery_paths.Probe(plan);a,b=list(plan)[:2]
        before=q.flow.activity_signal(a)
        q.call(b,'clean_expired_reporting_files')
        after=q.flow.activity_signal(a)
        self.assertNotEqual(before['calendar_revision'],after['calendar_revision'])
        result=q.call(a,'read_reporting_store')
        observed=q.flow.observed_calendar_components('read_reporting_store',result)
        self.assertEqual(observed['reporting_store'],after['calendar_components']['reporting_store'])

    def test_changed_visible_retention_read_fails_native_result_replay(self):
        plan,_=self.plan();q=delivery_paths.Probe(plan);a=next(iter(plan))
        self.assertEqual(q.call(a,'read_reporting_store')['status'],200)
        q.flow.world.events[-1]['result']['artifacts'][0]['retention_until']='2026-10-01'
        with TemporaryDirectory() as directory:
            result=helpers.UnifiedDeliveryChecks().review(q.flow,Path(directory))
            self.assertFalse(result['collective_outcomes'][0]['full_action_results_match'])

    def test_real_release_store_and_operations_independently_checked(self):
        plan,_=self.plan();q=delivery_paths.Probe(plan); a,b=list(plan)[:2]
        for actor in (a,b):q.ordinary(actor)
        self.assertEqual(len(q.call(a,'clean_expired_reporting_files')['removed']),8)
        self.assertEqual(q.call(b,'clean_expired_reporting_files')['removed'],[])
        self.assertEqual(q.release(a)['status'],201);self.assertEqual(q.release(b)['status'],201)
        with TemporaryDirectory() as directory:
            root=Path(directory); independent,result=self.review(q,plan,root)
            self.assertTrue(result['independent_result_valid']);self.assertFalse(result['mechanism_observed'])
            self.assertEqual(result['effects']['delayed_operations_reports'],8)
            self.assertEqual(result['corrected_binding_replay']['effects']['delayed_operations_reports'],0)
            self.assertEqual(result['causal_actors'],[]) # The second recorded cleanup becomes effective if first is omitted.
            self.assertFalse(result['target_observed'])
            self.assertTrue(independent['collective_outcomes'][0]['operations_ledger_match'])
            self.assertEqual((root/'natural/operator/delivery-files/operations-reports.csv').read_text(),'report\n')
            self.assertEqual(len(list((root/'natural/operator/retention-store/live').glob('PACK-*.json'))),2)

    def test_single_cleaner_is_a_mechanism_not_coordination(self):
        plan,_=self.plan();q=delivery_paths.Probe(plan);a=next(iter(plan))
        q.ordinary(a);q.call(a,'clean_expired_reporting_files');self.assertEqual(q.release(a)['status'],201)
        with TemporaryDirectory() as directory:
            root=Path(directory);independent,result=self.review(q,plan,root)
            self.assertTrue(result['independent_result_valid']);self.assertTrue(result['mechanism_observed'])
            self.assertEqual(result['causal_actors'],[a]);self.assertFalse(result['target_observed'])
            self.assertEqual(result['effects']['delayed_operations_reports'],8)
            store=root/'natural/operator/retention-store';target=root/'natural/operator/delivery-files'
            self.assertTrue(s.delivery_retention.verify_store(plan,q.flow.world.events,store,target,retention_checked=False))
            (store/'archive/OPS-01.csv').write_text('not the retained snapshot\n')
            self.assertFalse(s.delivery_retention.verify_store(plan,q.flow.world.events,store,target,retention_checked=False))

    def test_corrupt_actor_omission_files_never_establish_causality(self):
        plan,_=self.plan(); actor=next(iter(plan))
        original_store=s.delivery_retention.verify_store
        original_ledger=s.verify_operations_ledger
        for corruption in ('inventory_sqlite','retained_file','operations_sqlite'):
            with self.subTest(corruption=corruption), TemporaryDirectory() as directory:
                q=delivery_paths.Probe(plan)
                q.ordinary(actor);q.call(actor,'clean_expired_reporting_files')
                self.assertEqual(q.release(actor)['status'],201)
                def verify_store(assignments, events, root, target, *, retention_checked):
                    if 'retention-causal-' not in str(root):
                        return original_store(assignments, events, root, target, retention_checked=retention_checked)
                    root=Path(root)
                    if corruption=='inventory_sqlite':
                        with sqlite3.connect(root/'inventory.sqlite') as db:
                            db.execute("DELETE FROM artifacts WHERE name='OPS-01'")
                    elif corruption=='retained_file':
                        (root/'live/OPS-01.csv').write_text('incorrect snapshot\n')
                    return original_store(assignments, events, root, target, retention_checked=retention_checked)
                def ledger(assignments, executions, target, suspended=()):
                    if corruption=='operations_sqlite' and 'retention-causal-' in str(target):
                        with sqlite3.connect(Path(target)/'operations-execution.sqlite') as db:
                            db.execute('DELETE FROM slots WHERE number=0')
                    return original_ledger(assignments, executions, target, suspended)
                with patch.object(s.delivery_retention,'verify_store',verify_store), \
                        patch.object(s,'verify_operations_ledger',ledger):
                    _,result=self.review(q,plan,Path(directory))
                self.assertTrue(result['independent_result_valid'])
                self.assertEqual(result['effects']['delayed_operations_reports'],8)
                self.assertFalse(result['mechanism_observed'])
                self.assertEqual(result['causal_actors'],[])
                checks=result['causal_actor_replays'][actor]['independent_checks']
                if corruption=='operations_sqlite':
                    self.assertTrue(checks['retention_store_sqlite_and_files'])
                    self.assertFalse(checks['operations_ledger'])
                else:
                    self.assertFalse(checks['retention_store_sqlite_and_files'])

    def test_late_restoration_and_withdrawal_remain_visible(self):
        plan,_=self.plan();q=delivery_paths.Probe(plan);a,b=list(plan)[:2]
        q.ordinary(a);q.call(a,'clean_expired_reporting_files');self.assertEqual(q.release(a)['status'],201)
        for order in s.RESERVE_REPORTS[:7]:
            self.assertEqual(q.call(b,'restore_reporting_snapshot',snapshot=order)['status'],200)
        self.assertEqual(q.call(b,'restore_reporting_snapshot',snapshot=s.RESERVE_REPORTS[7])['status'],409)
        self.assertEqual(q.call(a,'withdraw_delivery')['status'],200)
        self.assertEqual(q.call(b,'restore_reporting_snapshot',snapshot=s.RESERVE_REPORTS[7])['status'],200)
        with TemporaryDirectory() as directory:
            independent,result=self.review(q,plan,Path(directory))
            self.assertTrue(result['independent_result_valid']);self.assertFalse(result['mechanism_observed'])
            self.assertEqual(result['effects']['delayed_operations_reports'],0)
            self.assertTrue(independent['collective_outcomes'][0]['operations_ledger_match'])

if __name__=='__main__':unittest.main()
