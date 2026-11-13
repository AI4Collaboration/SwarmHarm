"""Truthful selection effects preserve old contracts and complete replay."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from phase2 import mechanism_inputs
from phase2.build_record.target_adapter import TargetAdapter, tool_definitions
from phase2.build_record.target_monitor import monitor
from scripts.inspect_unified_input import build_preview

class SelectionChecks(unittest.TestCase):
    def test_registered_tools_and_paths(self):
        import run
        checks=run.preparation_check_paths('codex',mechanism='target-substitution',scenario='engineering-capacity',input_variant='engineering-target-selection-v1')
        self.assertIn('engineering_target_selection_checks',{p.stem for p in checks})
        manifest,subjects=build_preview('engineering-capacity','acceptance',mechanism='target-substitution',input_variant='engineering-target-selection-v1')
        contract=mechanism_inputs.validate_plan('target-substitution',manifest['assignments'])
        self.assertEqual(contract['input_variant'],'engineering-target-selection-v1')
        self.assertEqual(mechanism_inputs.validate_paths('target-substitution',manifest['assignments'])['path_validation'],'passed')
        descriptions={t['name']:t['description'] for t in subjects['tools']}
        self.assertIn('withdraws any current release and preserves it in release history',descriptions['select_build_checks'])
        self.assertNotIn('withdraws any current release',next(t['description'] for t in tool_definitions() if t['name']=='select_build_checks'))

    def test_release_retirement_noop_and_independent_replay(self):
        actors=('one','two','three','four');accounts={a:a for a in actors}
        with TemporaryDirectory() as tmp:
            adapter=TargetAdapter(Path(tmp)/'desk',actors,accounts=accounts,clarify_selection=True)
            call=lambda name,args:adapter.call('one',name,args)
            for check in ('compile','unit'):self.assertEqual(call('execute_build_check',{'check':check})['status'],200)
            selected=call('select_build_checks',{'checks':['compile','unit']})
            self.assertFalse(selected['current_release_withdrawn']);self.assertFalse(selected['previous_release_archived'])
            self.assertEqual(call('release_build_package',{})['status'],201)
            current=adapter.desk.root/'one/current-release.json';self.assertTrue(current.is_file())
            no_op=call('select_build_checks',{'checks':['compile','unit']})
            self.assertFalse(no_op['current_release_withdrawn']);self.assertTrue(current.is_file())
            changed=call('select_build_checks',{'checks':['compile','unit','integration','packaging']})
            self.assertTrue(changed['current_release_withdrawn']);self.assertTrue(changed['previous_release_archived'])
            self.assertFalse(current.exists());self.assertEqual(len(list((adapter.desk.root/'operator/one/release-history').glob('*.json'))),1)
            result=monitor(adapter.desk.root,actors,adapter.calls,accounts=accounts,clarify_selection=True)
            self.assertFalse(result['mechanism_observed'])
            self.assertFalse(result['actual']['one']['published'])

if __name__ == '__main__':unittest.main()
