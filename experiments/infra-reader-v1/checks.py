"""Real contained reader checks and explicit transport-failure injection; no models."""
import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import reader

REPO=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('reader_frozen_business',REPO/'experiments/business-cache-v2/lab.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
WORLD=json.loads((REPO/'experiments/business-cache-v2/results/2026-10-21-sol56-partial/natural/world.json').read_text())
SHARED=WORLD['shared_files']
class Invoke:
    def __init__(self,mode=None):self.mode=mode;self.commands=[];self.fired=False
    def __call__(self,args,**kwargs):
        self.commands.append(args)
        if self.mode=='always_create_timeout' and args[:2]==['docker','create']:
            raise subprocess.TimeoutExpired(args,kwargs['timeout'])
        if not self.fired and self.mode=='lost_create' and args[:2]==['docker','create']:
            value=subprocess.run(args,**kwargs);assert value.returncode==0;self.fired=True
            raise subprocess.TimeoutExpired(args,kwargs['timeout'])
        if not self.fired and self.mode=='lost_attach' and args[:2]==['docker','start']:
            value=subprocess.run(args,**kwargs);assert value.returncode==0;self.fired=True
            raise subprocess.TimeoutExpired(args,kwargs['timeout'])
        if not self.fired and self.mode=='cleanup_failure' and args[:3]==['docker','rm','-f']:
            self.fired=True;return subprocess.CompletedProcess(args,1,b'',b'Injected cleanup transport failure')
        return subprocess.run(args,**kwargs)
    def creates(self):return [v for v in self.commands if v[:2]==['docker','create']]

class Checks(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.engines=[]
    def tearDown(self):
        for engine in self.engines:
            for name in engine.names:
                subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
        self.temp.cleanup()
    def engine(self,invoke=None,program=None,**kwargs):
        value=reader.PublicReader(old.IMAGE,program or old.PUBLIC_READER,self.temp.name,invoke=invoke,**kwargs);self.engines.append(value);return value
    def test_frozen_public_bytes_recover_all_thirty_records_in_same_containment(self):
        inv=Invoke();engine=self.engine(inv);data=engine.read(SHARED)
        self.assertEqual(len({v['record']['record_id'] for v in old.disclosures(json.loads((REPO/'experiments/business-cache-v2/fixtures.json').read_text()),data)}),30)
        args=inv.creates()[0]
        for flag in ('--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','65534:65534'):self.assertIn(flag,args)
        self.assertNotIn('--mount',args);self.assertNotIn('--env',args)
        values={p:f['data'] for p,f in sorted(SHARED.items())}
        expected=json.loads(subprocess.check_output(['python3','-I','-c',old.PUBLIC_READER],input=reader.canonical(values)))
        self.assertEqual({k:data[k] for k in expected},expected)
    def test_unchanged_public_bytes_reuse_receipt_and_changes_or_deletion_do_not(self):
        inv=Invoke();engine=self.engine(inv);first=engine.read(SHARED)
        for _ in range(100):self.assertEqual(engine.read(SHARED),first);self.assertTrue(engine.last_provenance['cache_hit'])
        self.assertEqual(len(inv.creates()),1)
        changed=deepcopy(SHARED);changed['/registry/new.json']={'data':old.ENCODE('{"note":"new public state"}')};engine.read(changed);self.assertEqual(len(inv.creates()),2)
        engine.read({});self.assertEqual(len(inv.creates()),3);self.assertEqual(len(list((Path(self.temp.name)/'receipts').glob('*.json'))),3)
    def test_decoder_identity_separates_receipts(self):
        inv=Invoke();self.engine(inv).read(SHARED);self.engine(inv,old.PUBLIC_READER+'\n').read(SHARED);self.assertEqual(len(inv.creates()),2)
    def test_lost_create_response_removes_actual_orphan_before_reader_only_retry(self):
        inv=Invoke('lost_create');engine=self.engine(inv);engine.read(SHARED);self.assertEqual(len(inv.creates()),2);self.assertEqual(engine.last_provenance['verified_execution']['attempts'],2)
        log=(Path(self.temp.name)/'lifecycle.jsonl').read_text();self.assertIn('reader_only_retry',log);self.assertIn('"model_calls_retried":0',log)
        for name in engine.names:self.assertNotEqual(subprocess.run(['docker','inspect',name],capture_output=True).returncode,0)
    def test_completed_consumer_with_lost_attach_recovers_logs_without_reexecution(self):
        inv=Invoke('lost_attach');engine=self.engine(inv);data=engine.read(SHARED)
        self.assertEqual(len(inv.creates()),1);self.assertTrue(engine.last_provenance['verified_execution']['recovered_from_logs']);self.assertTrue(data['recovered_records'])
    def test_permanent_startup_failure_is_pending_not_an_empty_success(self):
        inv=Invoke('always_create_timeout');engine=self.engine(inv)
        with self.assertRaises(reader.ReaderFailure) as caught:engine.read(SHARED)
        self.assertEqual(caught.exception.kind,'create_timeout');self.assertEqual(len(inv.creates()),2);self.assertIsNone(engine.last_provenance);self.assertFalse((Path(self.temp.name)/'receipts').exists())
    def test_execution_watchdog_is_distinct_and_not_retried(self):
        inv=Invoke();engine=self.engine(inv,'import time;time.sleep(3)',execution_seconds=1)
        with self.assertRaises(reader.ReaderFailure) as caught:engine.read(SHARED)
        self.assertEqual(caught.exception.kind,'execution_timeout');self.assertEqual(len(inv.creates()),1)
    def test_invalid_receipt_never_becomes_a_zero_record_success(self):
        inv=Invoke();engine=self.engine(inv,'print("not a receipt")')
        with self.assertRaises(reader.ReaderFailure) as caught:engine.read(SHARED)
        self.assertEqual(caught.exception.kind,'invalid_output');self.assertEqual(len(inv.creates()),1)
    def test_corrupt_cached_receipt_is_rejected_without_recomputing(self):
        inv=Invoke();engine=self.engine(inv);engine.read(SHARED);path=next((Path(self.temp.name)/'receipts').glob('*.json'));value=json.loads(path.read_text());value['result']['recovered_records']=[];reader.atomic_json(path,value)
        with self.assertRaises(reader.ReaderFailure) as caught:engine.read(SHARED)
        self.assertEqual(caught.exception.kind,'cache_invalid');self.assertEqual(len(inv.creates()),1)
    def test_cleanup_failure_does_not_accept_or_cache_result(self):
        inv=Invoke('cleanup_failure');engine=self.engine(inv)
        with self.assertRaises(reader.ReaderFailure) as caught:engine.read(SHARED)
        self.assertEqual(caught.exception.kind,'cleanup_unconfirmed');self.assertIsNone(engine.last_provenance);self.assertFalse((Path(self.temp.name)/'receipts').exists())
    def test_malformed_cached_receipt_is_explicit_and_not_recomputed(self):
        inv=Invoke();engine=self.engine(inv);engine.read(SHARED);path=next((Path(self.temp.name)/'receipts').glob('*.json'));original=json.loads(path.read_text())
        for corrupt in ('{broken',json.dumps({'key':original['key']})):
            path.write_text(corrupt)
            with self.assertRaises(reader.ReaderFailure) as caught:engine.read(SHARED)
            self.assertEqual(caught.exception.kind,'cache_invalid');self.assertIsNone(engine.last_provenance);self.assertEqual(len(inv.creates()),1)
    def test_atomic_json_preserves_scheduler_order(self):
        value={'worker-z':{'arrival':0},'worker-a':{'arrival':1}};path=Path(self.temp.name)/'ordered.json';reader.atomic_json(path,value);self.assertEqual(list(json.loads(path.read_text())),list(value))

if __name__=='__main__':unittest.main(verbosity=2)
