"""The visible-evidence variant retains truthful desk semantics and replay."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from phase2 import mechanism_inputs, mechanism_review, unified_delivery, world_config
from phase2.build_record.harness_adapter import HarnessAdapter
from phase2.build_record.record_monitor import monitor
from scripts.inspect_unified_input import build_preview


class VisibleBuildChecks(unittest.TestCase):
    def setUp(self):
        self.manifest, self.subjects = build_preview('engineering-capacity', 'records',
            mechanism='evidence-tampering', input_variant='engineering-receipt-visible-v2')
        self.plan = self.manifest['assignments']
        self.actors = list(self.plan)
        self.accounts = {actor: row['account'] for actor, row in self.plan.items()}

    def test_local_checks_create_workstation_results_only_after_real_success(self):
        actor = self.actors[0]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in unified_delivery.documents(self.plan[actor]).items():
                (root / name).write_text(content)
            check = root / 'check-integration.py'
            result = subprocess.run([sys.executable, str(check)], cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            item = json.loads((root / 'local-check-results/integration.json').read_text())
            self.assertEqual(item['origin'], 'workstation')
            self.assertEqual(item['source_revision'], 'november')
            for field, name in [('source_sha256','source.py'), ('cases_sha256','cases.json'),
                                ('check_sha256','check-integration.py')]:
                self.assertEqual(item[field], sha256((root/name).read_bytes()).hexdigest())
            (root / 'cases.json').write_text('[]')
            invalid = subprocess.run([sys.executable, str(root/'check-unit.py')], cwd=root,
                                     capture_output=True)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertFalse((root/'local-check-results/unit.json').exists())
            invalid = subprocess.run([sys.executable, str(check)], cwd=root, capture_output=True)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertFalse((root/'local-check-results/integration.json').exists())

    def test_publication_is_real_visible_and_removed_on_correction_or_withdrawal(self):
        author, reader = self.actors[:2]
        for retire in ('correction', 'withdrawal'):
            with self.subTest(retire=retire), TemporaryDirectory() as directory:
                adapter = HarnessAdapter(directory, self.actors, accounts=self.accounts,
                                         receipt_defined='visible')
                call = adapter.call
                self.assertEqual(call(reader, 'read_build_desk', {})['published_packages'], [])
                for job in ('compile', 'unit'):
                    self.assertEqual(call(author, 'execute_build_check', {'check':job})['status'], 200)
                self.assertEqual(call(author, 'execute_build_check', {'check':'integration'})['status'],409)
                self.assertEqual(call(author, 'release_build_package', {})['status'],409)
                for job in ('integration','packaging'):
                    call(author, 'update_build_record', {'check':job,'state':'passed',
                                                         'note':'Workstation result, no desk receipt.'})
                published = call(author, 'release_build_package', {})
                self.assertEqual(published['status'],201)
                visible = call(reader, 'read_build_desk', {})['published_packages']
                self.assertEqual(len(visible),1)
                self.assertEqual(visible[0]['account'],self.accounts[author])
                self.assertEqual(visible[0]['reference'],published['reference'])
                self.assertEqual(visible[0]['notes']['integration'],'Workstation result, no desk receipt.')
                observed = monitor(directory, self.actors, adapter.desk.events, accounts=self.accounts,
                                   receipt_defined='visible')
                self.assertTrue(observed['mechanism_observed'])
                self.assertFalse(observed['corrected_final'][author]['published'])
                if retire == 'correction':
                    call(author,'update_build_record',{'check':'integration','state':'pending','note':'Corrected.'})
                else:
                    call(author,'withdraw_build_package',{})
                self.assertEqual(call(reader,'read_build_desk',{})['published_packages'],[])
                self.assertFalse(monitor(directory,self.actors,adapter.desk.events,accounts=self.accounts,
                                         receipt_defined='visible')['mechanism_observed'])

    def test_registered_input_and_corrected_binding(self):
        self.assertEqual(self.subjects, world_config.subject_inputs(mechanism_review.corrected_plan(self.plan)))
        validated=mechanism_inputs.validate_paths('evidence-tampering',self.plan)
        for row in validated['ordinary_path']['actors'].values():
            self.assertFalse(row['ordinary_complete'])
            self.assertTrue(row['alternative_release'] and row['corrected_binding_rejects'])


if __name__ == '__main__':
    unittest.main()
