import json,tempfile,time,unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import run,allowance

class Checks(unittest.TestCase):
    def state(self,p,credit='10'):
        run.base.save(p/'allowance.json',{'ceiling':credit,'remaining':credit,'spent':'0','spent_at_snapshot':'0','checked_at':time.time(),'admission_deadline':time.time()+60,'reservations':{}})
    def test_factorial_cells_are_unique_balanced(self):
        cells=run.cells();self.assertEqual(len(cells),8);self.assertEqual(len({json.dumps(c,sort_keys=True) for c in cells}),8)
        for key,value in [('repaired',True),('seconds',900),('model_name','glm')]:self.assertEqual(sum(c[key]==value for c in cells),4)
    def test_parallel_reservations_cannot_oversubscribe(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.state(p,'4')
            def attempt(i):
                try:return allowance.reserve(p,'1',p/str(i))
                except RuntimeError:return None
            with ThreadPoolExecutor(max_workers=8) as pool:tokens=list(pool.map(attempt,range(8)))
            self.assertEqual(sum(t is not None for t in tokens),4)
            self.assertEqual(allowance.available(json.loads((p/'allowance.json').read_text())),0)
    def test_actual_cost_settles_but_unknown_holds_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.state(p);token=allowance.reserve(p,'3',p/'journal')
            allowance.settle(p,token,'1');s=json.loads((p/'allowance.json').read_text());self.assertEqual(s['spent'],'1');self.assertFalse(s['reservations'])
            token=allowance.reserve(p,'3',p/'journal');allowance.settle(p,token,None,'timeout')
            s=json.loads((p/'allowance.json').read_text());self.assertIn(token,s['reservations']);self.assertTrue(s['hold'])
            with self.assertRaises(RuntimeError):allowance.reserve(p,'1',p/'new')
    def test_cost_over_bound_is_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.state(p);token=allowance.reserve(p,'1',p/'journal');allowance.settle(p,token,'2')
            s=json.loads((p/'allowance.json').read_text());self.assertIn(token,s['reservations']);self.assertTrue(s['hold'])
    def test_deadline_blocks_before_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.state(p);s=json.loads((p/'allowance.json').read_text());s['admission_deadline']=0;run.base.save(p/'allowance.json',s)
            with self.assertRaises(RuntimeError):allowance.reserve(p,'1',p/'journal')
    def test_initial_inputs_and_live_collector_unchanged(self):
        self.assertEqual(Path(run.BASE_COLLECT.__code__.co_filename).parent.name,'swarm-discovery-v3')
        old=json.loads((run.HERE.parent/'swarm-discovery-v3/VALIDATION.json').read_text())
        self.assertTrue(all(run.base.source_hashes()[k]==v for k,v in old['source_sha256'].items()))

    def test_guarded_transport_never_retries_unknown(self):
        class Parent:
            calls=0
            def __init__(self,journal):self.journal=journal;self.body={'max_tokens':2}
            def __call__(self,messages):self.calls+=1;raise TimeoutError('scripted unknown')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.state(p)
            cls=allowance.chat_class(Parent,p,{'prompt':'0.000001','completion':'0.000001'},100000)
            chat=cls(p/'journal.jsonl')
            with self.assertRaises(TimeoutError):chat([])
            self.assertEqual(chat.calls,1)
            state=json.loads((p/'allowance.json').read_text());self.assertTrue(state['hold']);self.assertEqual(len(state['reservations']),1)
    def test_shared_balance_refresh_rejects_before_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);self.state(p);state=json.loads((p/'allowance.json').read_text());state['checked_at']=0;run.base.save(p/'allowance.json',state)
            with patch('allowance.key_remaining',return_value=Decimal('0.1')):
                with self.assertRaises(RuntimeError):allowance.reserve(p,'1',p/'journal')
            self.assertFalse(json.loads((p/'allowance.json').read_text())['reservations'])
    def test_unscored_trials_never_enter_negative_denominator(self):
        from report import write
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);cell={'model_name':'deepseek','seconds':300,'repaired':False}
            write(p,[{'cell':cell,'summary':{'functional_communication_passed':None}},{'cell':cell,'summary':{'functional_communication_passed':False}}],'closed',{},[])
            row=json.loads((p/'report.json').read_text())['cells'][0]
            self.assertEqual((row['finished'],row['valid'],row['unscored'],row['successful']),(2,1,1,0))

if __name__=='__main__':unittest.main()
