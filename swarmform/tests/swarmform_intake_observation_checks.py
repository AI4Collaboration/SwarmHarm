"""Scheduling checks using exact process-read bytes, not model judgment."""
import base64
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from swarmform.intake_observation import intake_read_receipts
from swarmform.arrivals import IntakeSchedule, file_hashes

class IntakeObservationChecks(unittest.TestCase):
    def make(self, root, lines):
        blob='\n'.join(lines).encode(); digest=sha256(blob).hexdigest()
        (root/'blobs').mkdir(exist_ok=True);(root/'blobs'/digest).write_bytes(blob)
        raw=json.dumps({'files':{'000001.log':{'sha256':digest,'blob':'blobs/'+digest}}}).encode()
        (root/'observation.json').write_bytes(raw)
        return {'path':str(root/'observation.json'),'sha256':sha256(raw).hexdigest()}
    def line(self,path,data):
        encoded=''.join('\\x%02x'%x for x in data)
        return f'1 10.000000 read(3<{path}>, "{encoded}", 4096) = {len(data)}'
    def test_only_exact_nonempty_delivered_path_reads_count(self):
        with TemporaryDirectory() as folder:
            root=Path(folder); path='/workspace/intake/update/record.csv'
            reference=self.make(root,[self.line('/workspace/other.csv',b'abc'),self.line(path,b'wrong'),self.line(path,b''),self.line(path,b'abc')])
            seen=set();result=intake_read_receipts(reference,{path:b'abcdef\n'},seen)
            self.assertEqual(list(result),[path]);self.assertEqual(result[path]['bytes_read'],3)
            self.assertEqual(result[path]['scope'],'delivered_file_access_not_completion')
            self.assertEqual(intake_read_receipts(reference,{path:b'abcdef\n'},seen),{})
    def test_changed_evidence_fails_closed(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);reference=self.make(root,[self.line('/workspace/intake/update/r',b'abc')])
            next((root/'blobs').iterdir()).write_text('changed')
            with self.assertRaises(ValueError):intake_read_receipts(reference,{},set())
            (root/'observation.json').write_text('{}')
            with self.assertRaises(ValueError):intake_read_receipts(reference,{},set())
    def test_each_file_required_no_peer_or_future_notice_acknowledgment(self):
        private={a:{b:{f'intake/{b}/{n}.csv':f'{a},{b},{n}\n' for n in ('orders','postings')} for b in ('opening','update')} for a in ('A','B','C')}
        s=IntakeSchedule(private,{'opening':0,'update':1},activated_at=0)
        def reads(actor):return {'/workspace/'+p:{'bytes_read':1,'delivered_file_sha256':h} for p,h in file_hashes(private[actor]['update']).items()}
        self.assertEqual(s.acknowledge_reads('A',reads('A')),[])
        s.deliver_due(1,lambda a,b,f:file_hashes(f))
        partial=reads('A');partial.pop('/workspace/intake/update/orders.csv')
        self.assertEqual(s.acknowledge_reads('A',partial),[])
        self.assertEqual(s.acknowledge_reads('A',reads('B')),[])
        row=s.acknowledge_reads('A',reads('A'))
        self.assertEqual(len(row),1);self.assertIsNone(s.pending_notice('A'))
        self.assertEqual(s.acknowledge_reads('A',reads('A')),[])
        self.assertIsNotNone(s.pending_notice('B'));self.assertFalse(s.updates_accounted)
        for actor in ('B','C'):s.acknowledge_notice(s.pending_notice(actor))
        self.assertTrue(s.updates_accounted)
    def test_zero_bytes_or_wrong_version_remains_pending(self):
        private={'A':{b:{f'intake/{b}/data':'version'} for b in ('opening','update')}}
        s=IntakeSchedule(private,{'opening':0,'update':1},activated_at=0);s.deliver_due(1,lambda a,b,f:file_hashes(f))
        for size,digest in [(0,sha256(b'version').hexdigest()),(3,sha256(b'previous').hexdigest())]:
            self.assertEqual(s.acknowledge_reads('A',{'/workspace/intake/update/data':{'bytes_read':size,'delivered_file_sha256':digest}}),[])
        self.assertIsNotNone(s.pending_notice('A'))

if __name__=='__main__':unittest.main()
