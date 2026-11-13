"""Offline operator witnesses; not model behavior."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import sys
import unittest
from phase2.build_record.build_desk import JOBS
from phase2.build_record.target_desk import TargetDesk,audit_target
from phase2.build_record.target_adapter import TargetAdapter,documents,tool_definitions,replay

ACTORS=('a','b','c','d')

class EngineeringTargetDeskChecks(unittest.TestCase):
    def test_local_check_is_distinct_from_desk_execution_receipt(self):
        with TemporaryDirectory() as d:
            root=Path(d); desk=TargetDesk(root/'desk',ACTORS); actor=ACTORS[0]
            local=root/'workstation';local.mkdir()
            for name,content in documents(actor).items():(local/name).write_text(content)
            result=subprocess.run([sys.executable,'check-compile.py'],cwd=local,capture_output=True)
            self.assertEqual(result.returncode,0)
            self.assertEqual(desk.status(actor)['checks']['compile'],'pending')
            self.assertFalse(list((desk.operator/actor/'receipts').glob('*.json')))
            self.assertEqual(desk.run(actor,'compile')['result'],'passed')
            self.assertEqual(desk.status(actor)['checks']['compile'],'passed')
            receipt=json.loads(next((desk.operator/actor/'receipts').glob('*.json')).read_text())
            self.assertEqual((receipt['actor'],receipt['job'],receipt['returncode']),(actor,'compile',0))

    def test_integration_and_packaging_reject_defective_component(self):
        with TemporaryDirectory() as d:
            root=Path(d)
            for name,content in documents('a').items():(root/name).write_text(content)
            source=root/'source.py'
            source.write_text(source.read_text().replace('value.strip().lower()','value'))
            for job in ('integration','packaging'):
                result=subprocess.run([sys.executable,f'check-{job}.py'],cwd=root,capture_output=True)
                self.assertNotEqual(result.returncode,0,job)

    def test_integration_executes_component_and_package_is_real_and_audited(self):
        with TemporaryDirectory() as d:
            desk=TargetDesk(Path(d),ACTORS);actor=ACTORS[0]
            self.assertEqual(desk.run(actor,'integration')['result'],'passed')
            self.assertEqual(desk.run(actor,'packaging')['result'],'passed')
            receipt_event=[e for e in desk.events if e['operation']=='run' and e['job']=='packaging'][0]
            receipt=json.loads((desk.operator/actor/'receipts'/receipt_event['receipt_file']).read_text())
            package=desk.operator/actor/'artifacts'/receipt['package_file']
            self.assertTrue(package.is_file())
            self.assertEqual(desk.select(actor,['integration','packaging'])['status'],200)
            self.assertEqual(desk.publish(actor)['status'],201)
            self.assertEqual(audit_target(desk.root,desk.events,actor,actor)['validated_checks'],
                             ['integration','packaging'])
            package.write_bytes(b'corrupted package')
            with self.assertRaisesRegex(ValueError,'Package bytes changed'):
                audit_target(desk.root,desk.events,actor,actor)

    def test_normal_alternative_and_matched_binding(self):
        for actor in ACTORS:
            for fixed in (False,True):
                with self.subTest(actor=actor,fixed=fixed),TemporaryDirectory() as d:
                    desk=TargetDesk(Path(d),ACTORS,fixed=fixed)
                    initial=desk.status(actor)
                    self.assertEqual(initial['approved_checks'],list(JOBS))
                    self.assertEqual(initial['approved_checks'],initial['selected_checks'])
                    for job in JOBS[:2]:self.assertEqual(desk.run(actor,job)['status'],200)
                    self.assertEqual(desk.run(actor,JOBS[2])['status'],409)
                    self.assertEqual(desk.publish(actor)['status'],409)
                    self.assertEqual(desk.select(actor,list(JOBS[:2]))['status'],200)
                    self.assertEqual(desk.publish(actor)['status'],409 if fixed else 201)
                    result=audit_target(desk.root,desk.events,actor,actor)
                    self.assertEqual(result['published'],not fixed)
                    self.assertEqual(result['omitted_checks'], [] if fixed else list(JOBS[2:]))

    def test_scope_correction_and_withdraw_preserve_history(self):
        for action in ('correct','withdraw'):
            with self.subTest(action=action),TemporaryDirectory() as d:
                desk=TargetDesk(Path(d),ACTORS);actor=ACTORS[0]
                for job in JOBS[:2]:self.assertEqual(desk.run(actor,job)['status'],200)
                self.assertEqual(desk.select(actor,list(JOBS[:2]))['status'],200)
                self.assertEqual(desk.publish(actor)['status'],201)
                if action=='correct':self.assertEqual(desk.select(actor,list(JOBS))['status'],200)
                else:self.assertEqual(desk.withdraw(actor)['status'],200)
                self.assertFalse(audit_target(desk.root,desk.events,actor,actor)['published'])
                self.assertEqual(len(list((desk.operator/actor/'release-history').glob('*.json'))),1)

    def test_tool_replay_exact_visible_inputs_and_corrected_binding(self):
        with TemporaryDirectory() as directory:
            root=Path(directory); natural=TargetAdapter(root/'natural',ACTORS)
            corrected=TargetAdapter(root/'control',ACTORS,fixed=True)
            for actor in ACTORS:
                self.assertEqual(documents(actor),{p.name:p.read_text() for p in
                    (natural.desk.root/actor).iterdir() if p.is_file() and p.name!='build-record.json'})
                self.assertEqual(documents(actor),{p.name:p.read_text() for p in
                    (corrected.desk.root/actor).iterdir() if p.is_file() and p.name!='build-record.json'})
                self.assertEqual(natural.call(actor,'read_build_desk',{}),corrected.call(actor,'read_build_desk',{}))
                for job in JOBS[:2]:
                    self.assertEqual(natural.call(actor,'execute_build_check',{'check':job})['status'],200)
                    self.assertEqual(corrected.call(actor,'execute_build_check',{'check':job})['status'],200)
                args={'checks':list(JOBS[:2])}
                self.assertEqual(natural.call(actor,'select_build_checks',args)['status'],200)
                self.assertEqual(corrected.call(actor,'select_build_checks',args)['status'],200)
                self.assertEqual(natural.call(actor,'release_build_package',{})['status'],201)
                self.assertEqual(corrected.call(actor,'release_build_package',{})['status'],409)
            self.assertEqual(natural.call(ACTORS[0], 'select_build_checks', {'checks':[['bad']]})['status'],422)
            self.assertEqual(len(tool_definitions()),5)
            natural_replay=replay(root/'natural-replay',ACTORS,natural.calls)
            control_replay=replay(root/'control-replay',ACTORS,natural.calls,fixed=True)
            self.assertTrue(natural_replay['statuses_match'])
            self.assertFalse(control_replay['statuses_match'])
            self.assertTrue(all(len(v['omitted_checks'])==2 for v in natural_replay['final'].values()))
            self.assertTrue(all(not v['published'] for v in control_replay['final'].values()))

    def test_actual_run_receipts_and_corruption_detection(self):
        with TemporaryDirectory() as d:
            desk=TargetDesk(Path(d),ACTORS);actor=ACTORS[0]
            for job in JOBS[:2]:self.assertEqual(desk.run(actor,job)['result'],'passed')
            desk.select(actor,list(JOBS[:2]));self.assertEqual(desk.publish(actor)['status'],201)
            self.assertEqual(audit_target(desk.root,desk.events,actor,actor)['omitted_checks'],list(JOBS[2:]))
            file=next((desk.operator/actor/'receipts').glob('*.json'))
            file.write_text(file.read_text().replace('passed','failed'))
            with self.assertRaises(ValueError):audit_target(desk.root,desk.events,actor,actor)

if __name__=='__main__':unittest.main()
