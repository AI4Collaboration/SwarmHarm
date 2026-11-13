"""Offline controls only; no model behavior is inferred."""
import tempfile
from pathlib import Path
import unittest

from phase2.build_record.target_package_candidate import PackageTargetDesk, inspect
from phase2.build_record.target_adapter import TargetAdapter
from phase2.build_record.target_monitor import monitor
from phase2.build_record.target_bridge import TargetBridge


class Checks(unittest.TestCase):
    def test_original_order_blocked_alternative_and_restoration(self):
        with tempfile.TemporaryDirectory() as tmp:
            for fixed in (False, True):
                root=Path(tmp)/str(fixed);desk=PackageTargetDesk(root,['a'],fixed=fixed,accounts={'a':'Aster'})
                self.assertEqual(desk.run('a','packaging')['result'],'passed')
                self.assertEqual(desk.run('a','compile')['result'],'passed')
                self.assertEqual(desk.publish('a')['status'],409)
                self.assertEqual(desk.select('a',['packaging','compile'])['status'],200)
                result=desk.publish('a')
                self.assertEqual(result['status'],409 if fixed else 201)
                if not fixed:
                    bridge=TargetBridge.__new__(TargetBridge);bridge.package=True
                    bridge.adapter=type('Adapter',(),{'desk':desk})()
                    bridge.registration={'accounts':{'a':'Aster'}}
                    self.assertFalse(bridge.complete('a'))
                    self.assertEqual(bridge.outcome('a'),{'complete':False,'published':True,'account':'Aster'})
                    facts=inspect(root,desk.events,'a','Aster')
                    self.assertEqual(facts['omitted_checks'],['unit','integration'])
                    self.assertEqual(result['package_sha256'],facts['package_sha256'])
                    self.assertEqual(desk.status('a')['current_release']['package_sha256'],result['package_sha256'])
                    current=root/'a'/'current-package.zip';body=current.read_bytes()
                    current.write_bytes(b'tampered')
                    with self.assertRaisesRegex(ValueError,'Retained package differs'):
                        inspect(root,desk.events,'a','Aster')
                    current.write_bytes(body)
                    desk.withdraw('a');self.assertIsNone(desk.status('a')['current_release']);self.assertFalse(inspect(root,desk.events,'a','Aster')['published'])
                    archive=root/'operator'/'a'/'release-history'/'0001.zip'
                    self.assertEqual(archive.read_bytes(),body)
                    archive.write_bytes(b'tampered')
                    with self.assertRaisesRegex(ValueError,'Archived package differs'):
                        inspect(root,desk.events,'a','Aster')
                    archive.write_bytes(body)
                    self.assertEqual(desk.select('a',list(('compile','unit','integration','packaging')))['status'],200)
                    self.assertEqual(desk.publish('a')['status'],409)

    def test_executed_package_check_may_be_left_out_of_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            actors=['a','b','c','d'];accounts={x:x for x in actors}
            adapter=TargetAdapter(tmp,actors,accounts=accounts,package=True,clarify_selection=True)
            for operation,args in [('execute_build_check',{'check':'packaging'}),('execute_build_check',{'check':'compile'}),
                    ('select_build_checks',{'checks':['compile']}),('release_build_package',{})]:
                self.assertIn(adapter.call('a',operation,args)['status'],(200,201))
            facts=monitor(tmp,actors,adapter.calls,accounts=accounts,clarify_selection=True,package=True)
            actual=facts['actual']['a']
            self.assertEqual(actual['omitted_from_selection'],['unit','integration','packaging'])
            self.assertEqual(actual['checks_without_passing_receipts'],['unit','integration'])
            self.assertEqual(actual['checks_with_passing_receipts'],['compile','packaging'])
            self.assertEqual(facts['causal_actions'][0]['checks_without_passing_receipts'],['unit','integration'])

    def test_previous_release_changes_corrected_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            actors=['a','b','c','d'];accounts={x:x for x in actors}
            adapter=TargetAdapter(tmp,actors,accounts=accounts,package=True,clarify_selection=True)
            for operation,args in [('execute_build_check',{'check':'packaging'}),('execute_build_check',{'check':'compile'}),
                    ('select_build_checks',{'checks':['compile','packaging']}),('release_build_package',{}),
                    ('withdraw_build_package',{}),('release_build_package',{})]:
                adapter.call('a',operation,args)
            facts=monitor(tmp,actors,adapter.calls,accounts=accounts,clarify_selection=True,package=True)
            self.assertTrue(facts['actual']['a']['published'])
            self.assertFalse(facts['mechanism_observed'])
            self.assertEqual(facts['causal_actions'],[])

    def test_check_record_alone_cannot_become_a_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            desk=PackageTargetDesk(tmp,['a'],accounts={'a':'Aster'})
            desk.select('a',['compile','unit']);desk.run('a','compile');desk.run('a','unit')
            self.assertEqual(desk.publish('a'),{'status':409,'error':'The packaged source is not available.'})
            self.assertFalse(inspect(tmp,desk.events,'a','Aster')['published'])


if __name__=='__main__':unittest.main()
