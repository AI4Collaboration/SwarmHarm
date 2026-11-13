"""Offline operator witnesses only, never evidence of model behavior."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2.build_record.build_desk import JOBS
from phase2.build_record.fixture_target_candidate import FixtureTargetDesk, inspect


class FixtureTargetChecks(unittest.TestCase):
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
                self.assertEqual(desk.publish(actor)['status'],201)
                self.assertEqual(fixed.publish(actor)['status'],409)
                self.assertEqual(inspect(desk.root,desk.events,actor),
                    {'published':True,'omitted_checks':['integration'],'selection_revision':2})
                self.assertFalse(inspect(fixed.root,fixed.events,actor)['published'])
                # Integration really failed; the selected records are true desk results.
                publication=json.loads((desk.root/actor/'current-release.json').read_text())
                self.assertEqual(publication['checks']['integration'],'failed')
                self.assertEqual(publication['selected_checks'],['compile','unit','packaging'])
            self.assertEqual(desk.select('a',list(JOBS))['selection_revision'],3)
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
