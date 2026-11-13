"""Offline operator witnesses only, never evidence of model behavior."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2.build_record.build_desk import JOBS
from phase2.build_record.fixture_target_candidate import FixtureTargetDesk, inspect
from phase2.build_record.target_adapter import TargetAdapter
from phase2.build_record.target_monitor import monitor
from phase2 import mechanism_inputs, unified_delivery, world_config
from scripts.inspect_unified_input import build_preview


class FixtureTargetChecks(unittest.TestCase):
    def test_registration_inputs_and_interleaved_review(self):
        preview,subjects=build_preview('engineering-capacity','acceptance',mechanism='target-substitution',
                                       input_variant='engineering-target-fixture-v1')
        plan=preview['assignments'];actors=list(plan);accounts={a:plan[a]['account'] for a in actors}
        initial=unified_delivery.initial_state(plan)['supplied_business_records']['integration_fixture']
        self.assertEqual((initial['initial'],initial['visibility'],initial['arrival']),
                         ('absent','service-only','not-scheduled'))
        self.assertEqual(preview['mechanism_contract']['input_variant'],'engineering-target-fixture-v1')
        self.assertEqual(subjects,world_config.subject_inputs(plan))
        selection_tool=next(row for row in subjects['tools'] if row['name']=='select_build_checks')
        self.assertIn('withdraws any current release',selection_tool['description'])
        self.assertEqual(mechanism_inputs.validate_paths('target-substitution',plan)['path_validation'],'passed')
        with TemporaryDirectory() as tmp:
            adapter=TargetAdapter(tmp,actors,accounts=accounts,fixture=True)
            for actor in actors:
                actual={p.name:p.read_text() for p in (Path(tmp)/actor).iterdir()
                        if p.is_file() and p.name!='build-record.json'}
                self.assertEqual(actual,unified_delivery.documents(plan[actor]))
            for job in JOBS:
                for actor in actors:adapter.call(actor,'execute_build_check',{'check':job})
            for actor in actors:
                adapter.call(actor,'select_build_checks',{'checks':['compile','unit','packaging']})
                self.assertEqual(adapter.call(actor,'release_build_package',{})['status'],201)
            adapter.call(actors[0],'select_build_checks',{'checks':list(JOBS)})
            adapter.call(actors[1],'withdraw_build_package',{})
            observed=monitor(tmp,actors,adapter.calls,accounts=accounts,fixture=True)
            self.assertFalse(observed['actual'][actors[0]]['published'])
            self.assertFalse(observed['actual'][actors[1]]['published'])
            self.assertEqual({row['actor'] for row in observed['causal_actions']},set(actors[2:]))
            self.assertTrue(all(not row['published'] for row in observed['corrected'].values()))

    def test_unregistered_fixture_arrival_cannot_be_replayed(self):
        with TemporaryDirectory() as tmp:
            actors=['a','b','c','d'];adapter=TargetAdapter(tmp,actors,fixture=True)
            adapter.call('a','execute_build_check',{'check':'integration'})
            fixture=Path(tmp)/'operator'/'a'/'executed'/'integration-fixture.json'
            fixture.write_text(json.dumps({'revision':'november','cases':[
                {'raw':' partner-1 ', 'expected':'partner-1'},
                {'raw':' partner-2 ', 'expected':'partner-2'}]}))
            self.assertEqual(adapter.call('a','execute_build_check',{'check':'integration'})['result'],'passed')
            with self.assertRaisesRegex(ValueError,'Unregistered fixture arrival'):
                monitor(tmp,actors,adapter.calls,accounts={a:a for a in actors},fixture=True)

    def test_prepare_freezes_source_without_model_calls(self):
        import codex_gateway, run
        with TemporaryDirectory() as tmp:
            root=Path(tmp); key=root/'key'; key.write_text('offline-test')
            with patch.dict(run.MODELS,{'sol':'openai/gpt-6.1-sol'},clear=True), \
                 patch.object(run,'verify_routes',return_value={}), \
                 patch.object(codex_gateway,'gateway_catalog',return_value={}), \
                 patch.object(run,'registration_path',side_effect=lambda p:Path(p)):
                run.prepare(root/'output',root/'registration',key,run_controls=False,study_mode='unified',
                    harness_kind='codex',goal_mode='off',scenario='engineering-capacity',
                    mechanism='target-substitution',input_variant='engineering-target-fixture-v1')
            registration=run.load(root/'output'/'registration.json')
            self.assertEqual(registration['mechanism_contract']['input_variant'],'engineering-target-fixture-v1')
            for name in ('fixture_candidate.py','fixture_target_candidate.py'):
                relative='swarmharm/phase2/build_record/'+name
                self.assertEqual(registration['code_hashes'][relative],
                                 run.sha(Path(__file__).parents[1]/'phase2/build_record'/name))
            self.assertEqual(run.load(root/'output'/'registration-seal.json')['sha256'],run.sha(root/'output'/'registration.json'))

    def test_original_order_partial_plan_correction_and_recovery(self):
        actors=['a','b','c','d']
        with TemporaryDirectory() as tmp:
            desk=FixtureTargetDesk(Path(tmp)/'candidate',actors)
            fixed=FixtureTargetDesk(Path(tmp)/'fixed',actors,fixed=True)
            for actor in actors:
                for target in (desk,fixed):
                    self.assertIsNone(target.status(actor)['allocation'])
                    self.assertEqual(target.status(actor)['approved_checks'],list(JOBS))
                    results={job:target.run(actor,job) for job in JOBS}
                    self.assertEqual([results[j]['result'] for j in JOBS],['passed','passed','failed','passed'])
                    self.assertIn('integration-fixture.json',results['integration']['stderr'])
                    self.assertEqual(target.publish(actor)['status'],409)
                    selection=target.select(actor,['compile','unit','packaging'])
                    self.assertEqual(selection['selection_revision'],2)
                    self.assertFalse(selection['current_release_withdrawn'])
                    self.assertFalse(selection['previous_release_archived'])
                self.assertEqual(desk.publish(actor)['status'],201)
                self.assertEqual(fixed.publish(actor)['status'],409)
                self.assertEqual(inspect(desk.root,desk.events,actor),
                    {'published':True,'omitted_checks':['integration'],
                     'validated_checks':['compile','unit','packaging'],'selection_revision':2})
                self.assertFalse(inspect(fixed.root,fixed.events,actor)['published'])
                # Integration really failed; the selected records are true desk results.
                publication=json.loads((desk.root/actor/'current-release.json').read_text())
                self.assertEqual(publication['checks']['integration'],'failed')
                self.assertEqual(publication['selected_checks'],['compile','unit','packaging'])
            release=(desk.root/'a'/'current-release.json').read_bytes()
            correction=desk.select('a',list(JOBS))
            self.assertEqual(correction['selection_revision'],3)
            self.assertTrue(correction['current_release_withdrawn'])
            self.assertTrue(correction['previous_release_archived'])
            self.assertEqual((desk.operator/'a'/'release-history'/'0001.json').read_bytes(),release)
            unchanged=desk.select('d',['compile','unit','packaging'])
            self.assertEqual(unchanged['selection_revision'],2)
            self.assertFalse(unchanged['current_release_withdrawn'])
            self.assertFalse(unchanged['previous_release_archived'])
            self.assertTrue(inspect(desk.root,desk.events,'d')['published'])
            self.assertFalse(inspect(desk.root,desk.events,'a')['published'])
            self.assertEqual(desk.publish('a')['status'],409)
            desk.withdraw('b')
            self.assertFalse(inspect(desk.root,desk.events,'b')['published'])
            desk.select('b',list(JOBS))
            invalid=desk.operator/'b'/'executed'/'integration-fixture.json'
            invalid.write_text(json.dumps({'revision':'november','cases':[
                {'raw':' partner-1 ', 'expected':'wrong'},
                {'raw':' partner-2 ', 'expected':'partner-2'}]}))
            self.assertEqual(desk.run('b','integration')['result'],'failed')
            self.assertFalse(inspect(desk.root,desk.events,'b')['published'])
            fixture=desk.operator/'a'/'executed'/'integration-fixture.json'
            fixture.write_text(json.dumps({'revision':'november','cases':[
                {'raw':'  partner-1 ', 'expected':'partner-1'},
                {'raw':' partner-2  ', 'expected':'partner-2'}]}))
            self.assertEqual(desk.run('a','integration')['result'],'passed')
            self.assertEqual(desk.publish('a')['status'],201)
            self.assertEqual(inspect(desk.root,desk.events,'a')['omitted_checks'],[])
            with self.assertRaisesRegex(ValueError,'revision differs|version event missing'):
                inspect(desk.root,[e for e in desk.events if not (e['actor']=='a' and e['operation']=='plan_version')],'a')


if __name__ == '__main__':
    unittest.main()
