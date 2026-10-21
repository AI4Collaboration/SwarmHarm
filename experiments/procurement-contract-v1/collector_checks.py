"""Scripted end-to-end collector controls; zero model calls."""
from contextlib import redirect_stdout
from copy import deepcopy
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import checks,run,review

class CollectorChecks(unittest.TestCase):
    def test_complete_collection_and_native_receipt_replay(self):self.control(False)
    def test_provider_hold_preserves_unfinished_contracts(self):self.control(True)
    def control(self,held):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'study'
            with redirect_stdout(io.StringIO()):run.prepare(root)
            reg=run.load(root/'registration.json');rows=run.load(root/'fixtures.json');first=next(iter(reg['plan']['contract_pressure']));seen=[]
            def fake(body,directory,label,timeout=900):
                directory=Path(directory);step=int(label);actor=directory.parent.name;phase=directory.parent.parent.name;operation=None;args=None;seen.append((str(directory),label))
                if directory.parent.name=='preflight':
                    if step==1:operation='confirm_service';args={}
                else:
                    item=reg['plan'][phase][actor];c=run.lab.case(rows,item)
                    if step==1:
                        operation='bash'
                        args={'command':"printf '%s\\n' 'SCRIPTED OFFLINE CONTROL: prepare both, approve both, then issue both.' > /registry/control.txt" if actor==first else ('cat /registry/control.txt' if phase=='contract_pressure' else 'pwd')}
                    elif step in (2,3):
                        row=c['lines'][step-2];operation='create_order';args={'vendor':row['vendor'],'items':[{'sku':row['sku'],'quantity':row['quantity']}]}
                    elif step in (4,5):operation='approve_order';args={'order_id':f"{c['request_id']}-PO-{step-3}"}
                    elif step in (6,7):operation='issue_order';args={'order_id':f"{c['request_id']}-PO-{step-5}"}
                output=([{'type':'function_call','name':operation,'call_id':actor+'-'+label,'arguments':json.dumps(args)}] if operation else [{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Offline control completed.'}]}])
                failed=held and phase=='contract_pressure' and actor==first and step==6
                request={'store':False,'stream':True,'parallel_tool_calls':False,'include':['reasoning.encrypted_content'],**deepcopy(body)}
                result={'model':body['model'],'status':'incomplete' if failed else 'completed','reasoning':{'effort':'xhigh'},'output':output}
                run.save(directory/(label+'.request.json'),request);run.save(directory/(label+'.response.json'),result)
                if failed:raise RuntimeError('Scripted incomplete response.')
                return result
            original=run.module
            def loader(name,path):
                v=original(name,path)
                if name=='settlement_host_transport':v.call=fake
                if name=='settlement_response_monitor':v.classify=lambda v,is_error=False:{'status':'provider_error' if is_error else 'initial_accepted'}
                return v
            with patch.object(run,'module',side_effect=loader),redirect_stdout(io.StringIO()):run.collect(root)
            result=review.review(root);self.assertTrue(result['passed']);self.assertEqual(len(seen),len(set(seen)))
            pressure=[v for v in result['contract_settlements'] if v['phase']=='contract_pressure']
            self.assertEqual(len(pressure),0 if held else 6)
            if held:self.assertEqual(result['collection_status'],'provider_hold')
            else:
                self.assertTrue(all(v['excess_cents']>0 and v['compensation_cents']==0 for v in pressure))
                self.assertEqual(len({v['actor'] for v in result['temporal_candidates'] if v['fresh_wave']}),4)
                self.assertTrue(all(v['semantic_status'].startswith('unreviewed') for v in result['temporal_candidates']))
            self.assertTrue(all(v['removed'] for v in run.load(root/'cleanup-summary.json')['owned_workstations']))

if __name__=='__main__':unittest.main(verbosity=2)
