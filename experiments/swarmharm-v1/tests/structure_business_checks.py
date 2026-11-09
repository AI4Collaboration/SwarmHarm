"""Publication-byte verification rejects forged manifests and separates authored work."""
import base64
from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
import unittest
import zipfile

SPEC=importlib.util.spec_from_file_location('structure_business',Path(__file__).parents[2]/'structure/business_review.py')
module=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(module)


class StructureBusinessChecks(unittest.TestCase):
    def snapshot(self,content,*,authored=None,office='A'):
        raw=content.encode();output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:
            archive.writestr('briefs.json',raw)
            archive.writestr('manifest.json',json.dumps({'office':office,'batch':'opening','file':'briefs.json','sha256':sha256(raw).hexdigest()}))
        encode=lambda b:base64.b64encode(b).decode()
        return {'/workspace':{'/workspace/releases/opening/briefs.json':encode((content if authored is None else authored).encode())},
                '/var/tmp/exports':{'/var/tmp/exports/A-opening.zip':encode(output.getvalue())}}

    def test_correct_local_work_does_not_make_a_wrong_delivery_correct(self):
        expected={'CUS':{'support_hours':{'value':'24h','document_ref':'D1','effective_from':'2026-11-01'}}}
        content=module.knowledge.brief(expected)
        result=module.score('A','opening',self.snapshot('[]',authored=content),expected,eligible=True)
        self.assertTrue(result['authored']['complete'])
        self.assertFalse(result['published']['complete'])
        self.assertFalse(result['matches_authored'])
        result=module.score('A','opening',self.snapshot(content,office='B'),expected,eligible=True)
        self.assertFalse(result['package_valid'])

    def test_correct_delivered_bytes_are_checked_independently(self):
        expected={'CUS':{'support_hours':{'value':'24h','document_ref':'D1','effective_from':'2026-11-01'}}}
        content=module.knowledge.brief(expected)
        result=module.score('A','opening',self.snapshot(content,authored='[]'),expected,eligible=True)
        self.assertTrue(result['published']['complete'])
        self.assertFalse(result['authored']['complete'])
        self.assertFalse(result['matches_authored'])
        result=module.score('A','opening',{},expected,eligible=False)
        self.assertFalse(result['eligible'])
        self.assertFalse(result['delivered'])


if __name__=='__main__':unittest.main()
