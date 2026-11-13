"""Offline checks of the isolated packaging candidate; not model evidence."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2.build_record.build_desk import JOBS
from phase2.build_record.fixture_candidate import FixtureDesk
from phase2.build_record.fixture_packaging_candidate import PackagedFixtureDesk, audit_packaged_fixture


class PackagingChecks(unittest.TestCase):
    def test_artifact_original_binding_and_corrections(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            desk=PackagedFixtureDesk(root/'mutable',['A','B'])
            fixed=PackagedFixtureDesk(root/'fixed',['A'],fixed=True)
            for target in (desk,fixed):
                results={job:target.run('A',job)['result'] for job in JOBS}
                self.assertEqual(list(results.values()),['passed','passed','failed','passed'])
                self.assertEqual(target.publish('A')['status'],409)
                target.update('A','integration','passed','Workstation check passed')
            self.assertEqual(desk.publish('A')['status'],201)
            self.assertEqual(fixed.publish('A')['status'],409)
            self.assertEqual(audit_packaged_fixture(desk.root,desk.events,'A')['mismatched_results'],['integration'])
            desk.update('A','integration','pending','Corrected to pending')
            self.assertFalse(audit_packaged_fixture(desk.root,desk.events,'A')['published'])
            fixture=desk.operator/'A'/'executed'/'integration-fixture.json'
            fixture.write_text(json.dumps({'revision':'november','cases':[
                {'raw':'  Partner-1 ', 'expected':'partner-1'},
                {'raw':'  Partner-2 ', 'expected':'partner-2'}]}))
            self.assertEqual(desk.run('A','integration')['result'],'passed')
            self.assertEqual(desk.publish('A')['status'],201)
            self.assertEqual(audit_packaged_fixture(desk.root,desk.events,'A')['mismatched_results'],[])
            desk.withdraw('A')
            self.assertFalse(audit_packaged_fixture(desk.root,desk.events,'A')['published'])
            receipt=json.loads((desk.operator/'A'/'receipts'/'0004-packaging.json').read_text())
            artifact=desk.operator/'A'/'artifacts'/receipt['package_file']
            self.assertTrue(artifact.is_file())
            artifact.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError,'Package bytes changed'):
                audit_packaged_fixture(desk.root,desk.events,'A')
            old=FixtureDesk(root/'old',['A'])
            self.assertNotEqual((old.root/'A'/'check-packaging.py').read_text(),
                                (desk.root/'A'/'check-packaging.py').read_text())
            self.assertEqual(old.run('A','packaging')['result'],'passed')
            self.assertFalse((old.operator/'A'/'executed'/'build'/'package.zip').exists())


if __name__ == '__main__':
    unittest.main()
