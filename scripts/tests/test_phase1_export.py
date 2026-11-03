"""Offline export boundaries, including an explicitly frozen evaluator."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,SCRIPTS/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
exporter=module('export_phase1_evidence');verifier=module('verify_phase1_export')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v))

class ExportChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.rollout=self.root/'rollout';self.rollout.mkdir()
        (self.rollout/'raw.json').write_text('{}')
        save(self.rollout/'evidence-manifest.json',{'files':{'raw.json':digest(self.rollout/'raw.json')}})
        save(self.rollout/'review-manifest.json',{'terminal_manifest_sha256':digest(self.rollout/'evidence-manifest.json'),'review_files':{}})
        self.snapshot=self.root/'frozen'/'source';self.snapshot.mkdir(parents=True)
        (self.snapshot/'code.py').write_text('VALUE = 1\n')
        save(self.snapshot.parent/'source-hashes.json',{'code.py':digest(self.snapshot/'code.py')})
        self.out=self.root/'export'
    def export(self,**kwargs):return exporter.export(self.out,[self.rollout],**kwargs)
    def refresh_mapping_hash(self):
        p=self.out/'manifest.json';m=json.loads(p.read_text());m['mapping.json']=digest(self.out/'mapping.json');save(p,m)
    def test_explicit_source_is_copied_and_bound(self):
        result=self.export(replay_source=self.snapshot)
        self.assertTrue(result['explicit_replay_source'])
        self.assertEqual(verifier.verify(self.out)['rollouts'],1)
        mapping=json.loads((self.out/'mapping.json').read_text())['replay_source']
        self.assertEqual((self.out/mapping['portable_snapshot']/'code.py').read_bytes(),(self.snapshot/'code.py').read_bytes())
    def test_credential_aborts_before_creation(self):
        secret=b'unique-secret-value';(self.rollout/'raw.json').write_bytes(secret)
        save(self.rollout/'evidence-manifest.json',{'files':{'raw.json':digest(self.rollout/'raw.json')}})
        save(self.rollout/'review-manifest.json',{'terminal_manifest_sha256':digest(self.rollout/'evidence-manifest.json'),'review_files':{}})
        with self.assertRaisesRegex(ValueError,'Credential'):self.export(secrets=[secret])
        self.assertFalse(self.out.exists())
    def test_missing_binding_cannot_supply_evaluator_code(self):
        self.export(replay_source=self.snapshot)
        p=self.out/'manifest.json';m=json.loads(p.read_text());del m['validators/frozen/source/code.py'];save(p,m)
        with self.assertRaisesRegex(ValueError,'Replay-source file is not bound'):verifier.verify(self.out,replay=True)
    def test_mapping_cannot_escape_package(self):
        self.export();p=self.out/'mapping.json';m=json.loads(p.read_text());m['rollouts'][0]['portable_root']='../rollout';save(p,m);self.refresh_mapping_hash()
        with self.assertRaisesRegex(ValueError,'Escaping portable mapping'):verifier.verify(self.out)
    def test_source_cannot_escape_snapshot(self):
        (self.snapshot.parent/'outside.py').write_text('VALUE = 2')
        save(self.snapshot.parent/'source-hashes.json',{'../outside.py':digest(self.snapshot.parent/'outside.py')})
        with self.assertRaisesRegex(ValueError,'escapes'):self.export(replay_source=self.snapshot)
        self.assertFalse(self.out.exists())
    def test_duplicate_roots_do_not_overwrite(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):exporter.export(self.out,[self.rollout,self.rollout])
        self.assertFalse(self.out.exists())

if __name__=='__main__':unittest.main()
