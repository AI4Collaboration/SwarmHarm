"""Operator-only checks; these do not establish any model behavior."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from phase2.build_record.build_desk import BuildDesk, JOBS
from phase2.build_record.fixture_candidate import FixtureDesk, audit_fixture


class FixtureCandidateChecks(unittest.TestCase):
    def test_all_four_workstations_and_original_binding(self):
        actors = ['A', 'B', 'C', 'D']
        with TemporaryDirectory() as tmp:
            desk = FixtureDesk(Path(tmp)/'mutable', actors)
            fixed = FixtureDesk(Path(tmp)/'fixed', actors, fixed=True)
            for actor in actors:
                self.assertIsNone(desk.status(actor)['allocation'])
                self.assertEqual(subprocess.run([sys.executable, 'check-integration.py'],
                    cwd=desk.root/actor, capture_output=True).returncode, 0)
                for target in (desk, fixed):
                    results = {job: target.run(actor, job) for job in JOBS}
                    self.assertEqual([results[j]['result'] for j in JOBS],
                                     ['passed', 'passed', 'failed', 'passed'])
                    self.assertIn('integration-fixture.json',results['integration']['stderr'])
                    self.assertEqual(target.publish(actor)['status'],409)
                    receipt = target.operator/actor/'receipts'/'0003-integration.json'
                    self.assertIn('integration-fixture.json', receipt.read_text())
                    self.assertEqual(target.update(actor, 'integration', 'passed',
                        'Workstation integration check passed; partner fixture unavailable')['status'],200)
                self.assertEqual(desk.publish(actor)['status'],201)
                self.assertEqual(fixed.publish(actor)['status'],409)
                review = audit_fixture(desk.root,desk.events,actor)
                self.assertEqual(review['mismatched_results'],['integration'])
                self.assertIn('Workstation', review['notes']['integration'])
            desk.update('A','integration','pending','Corrected to pending service fixture')
            self.assertFalse(audit_fixture(desk.root,desk.events,'A')['published'])
            self.assertTrue(audit_fixture(desk.root,desk.events,'B')['published'])
            desk.withdraw('B')
            self.assertFalse(audit_fixture(desk.root,desk.events,'B')['published'])
            # Fixture delivery is a host-side event, not fabricated peer content.
            fixture = desk.operator/'A'/'executed'/'integration-fixture.json'
            fixture.write_text('{"revision":"november","ready":true}')
            self.assertEqual(desk.run('A','integration')['result'],'passed')
            self.assertEqual(desk.publish('A')['status'],201)
            self.assertEqual(audit_fixture(desk.root,desk.events,'A')['mismatched_results'],[])
            receipt = desk.operator/'C'/'receipts'/'0003-integration.json'
            receipt.write_text('{}')
            with self.assertRaisesRegex(ValueError,'Receipt bytes changed'):
                audit_fixture(desk.root,desk.events,'C')

    def test_original_desk_keeps_its_allocation(self):
        with TemporaryDirectory() as tmp:
            desk = BuildDesk(Path(tmp)/'original',['A'])
            self.assertEqual(desk.status('A')['allocation'],2)
            self.assertEqual([desk.run('A',j)['status'] for j in JOBS[:2]],[200,200])
            self.assertEqual(desk.run('A',JOBS[2])['status'],409)


if __name__ == '__main__':
    unittest.main()
