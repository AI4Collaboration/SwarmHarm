"""Retained attempts and population selection must not repeat study work."""
import json
from pathlib import Path
import tempfile
import unittest

import batch_resume as resume


class BatchResumeChecks(unittest.TestCase):
    def row(self, population=4, **changes):
        return dict(model='openai/gpt-6.1-sol', population=population, replicate=1,
                    task='service-plan', channel='direct', seconds=600,
                    source_sha256='current-source', **changes)

    def retained(self, root, row):
        output = root/'model/n4/finished'
        output.mkdir(parents=True)
        (output/'registration.json').write_text('{"frozen":"original source"}')
        record = {**row, 'output':str(output), 'status':'complete', 'registration':str(output)}
        resume.write(root/'retained-attempts.json', {'attempts':[
            {'settings':row, 'path':'model/n4/finished', 'record':record}]})
        return output

    def test_retained_source_and_files_survive_population_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = self.row();old['source_sha256']='sealed-old-source'
            output = self.retained(root,old)
            original = (output/'registration.json').read_bytes()
            self.assertEqual(resume.prepare(root,[self.row()],True),[old])
            new = self.row(8)
            self.assertEqual(resume.prepare(root,[new],True),[new])
            plan = json.loads((root/'plan.json').read_text())
            self.assertEqual(plan,[old,new])
            self.assertEqual(resume.prepare(root,[self.row()],True),[old])
            self.assertEqual((output/'registration.json').read_bytes(),original)

    def test_changed_budgets_cannot_reuse_an_existing_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.retained(root,self.row())
            changed=self.row();changed['seconds']=300
            with self.assertRaisesRegex(ValueError,'settings differ'):
                resume.prepare(root,[changed],True)
            self.assertFalse((root/'plan.json').exists())

    def test_missing_or_external_retained_attempt_is_not_restarted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in ('missing','..'):
                resume.write(root/'retained-attempts.json',{'attempts':[
                    {'settings':self.row(),'path':path,'record':{}}]})
                with self.assertRaisesRegex(ValueError,'missing or outside'):
                    resume.prepare(root,[self.row()],True)

    def test_tracking_keeps_other_populations_and_real_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);row=self.row();output=self.retained(root,row)
            resume.save_index(root,'swarmharm',[{**row,'status':'collected',
                'output':str(output),'registration':'invented-current-directory'}])
            resume.save_index(root,'swarmharm',[{**self.row(8),'status':'running'}])
            runs=json.loads((root/'index.json').read_text())['runs']
            self.assertEqual([r['population'] for r in runs],[4,8])
            self.assertEqual(runs[0]['registration'],str(output))
            self.assertTrue(runs[0]['retained_attempt'])

    def test_direct_component_keeps_strict_plan_check_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);resume.prepare(root,[self.row()])
            with self.assertRaisesRegex(ValueError,'different plan'):
                resume.prepare(root,[self.row(8)])


if __name__=='__main__':
    unittest.main()
