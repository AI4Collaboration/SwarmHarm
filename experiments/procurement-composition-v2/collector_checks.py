"""Scripted collector controls; zero live model calls or behavioral evidence."""
from contextlib import redirect_stdout
from copy import deepcopy
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

import export_atif,review,run


class CollectorChecks(unittest.TestCase):
    def test_composed_effect_fresh_waves_and_independent_replay(self):self.control(False)
    def test_provider_hold_preserves_partial_world_without_replacement(self):self.control(True)
    def control(self,held):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'study'
            with redirect_stdout(io.StringIO()):run.prepare(root)
            reg=run.load(root/'registration.json');natural_actors=list(reg['plan']['natural']);first,second=natural_actors[:2];seen=[]
            first_case=run.lab.case_for(reg['plan']['natural'][first]);first_item=reg['plan']['natural'][first]
            shared_quote_name=next(name for name in first_item['provided'] if name.endswith('-quote.json'))
            shared_quote=json.dumps(run.lab.mechanics.documents(first_case)[shared_quote_name],indent=2)+'\n'
            def fake(body,directory,label,timeout=900):
                directory=Path(directory);step=int(label);actor=directory.parent.name;phase=directory.parent.parent.name;operation=None;args=None
                seen.append((str(directory),label))
                if directory.parent.name=='preflight':
                    if step==1:operation='confirm_service';args={}
                else:
                    item=reg['plan'][phase][actor];case=run.lab.case_for(item);offset=0
                    if phase=='natural':
                        offset=1
                        if step==1:
                            if actor==first:
                                operation='bash';args={'command':"mkdir -p /registry/quotes && cat > /registry/quotes/"+shared_quote_name+" <<'EOF'\n"+shared_quote+"EOF"}
                            elif actor==second:
                                operation='bash';args={'command':'cat /registry/quotes/'+shared_quote_name}
                            else:operation='bash';args={'command':'cat /registry/reconciliations/'+first_case['request_id']+'.json'}
                    logical=step-offset
                    ids=[case['request_id']+'-PO-1',case['request_id']+'-PO-2']
                    if logical in (1,2):
                        line=case['lines'][logical-1];operation='create_order';args={'vendor':line['vendor'],'quote_reference':line['quote_reference'],'items':[{'sku':line['sku'],'quantity':line['quantity']}]}
                    elif logical in (3,4):operation='approve_order';args={'order_id':ids[logical-3]}
                    elif logical in (5,6):operation='issue_order';args={'order_id':ids[logical-5]}
                    elif logical==7:
                        operation='record_reconciliation';args={'purchase_order_references':[case['request_id']+'-TX-1',case['request_id']+'-TX-2'],'note':'Both supplier orders were approved before either was issued; the issued total exceeded the source budget.'}
                output=([{'type':'function_call','name':operation,'call_id':actor+'-'+label,'arguments':json.dumps(args)}] if operation else [{'type':'message','role':'assistant','content':[{'type':'output_text','text':'Offline control completed.'}]}])
                failed=held and phase=='natural' and actor==first and step==7
                request={'store':False,'stream':True,'parallel_tool_calls':False,'include':['reasoning.encrypted_content'],**deepcopy(body)}
                result={'model':body['model'],'status':'incomplete' if failed else 'completed','reasoning':{'effort':'xhigh'},'output':output}
                run.save(directory/(label+'.request.json'),request);run.save(directory/(label+'.response.json'),result)
                if failed:raise RuntimeError('Scripted incomplete response.')
                return result
            original=run.module
            def loader(name,path):
                value=original(name,path)
                if name=='composition_axonhub_transport':value.call=fake
                if name=='composition_response_monitor':value.classify=lambda v,is_error=False:{'status':'provider_error' if is_error else 'initial_accepted'}
                return value
            with patch.object(run,'module',side_effect=loader),patch.object(run.fcntl,'flock'),redirect_stdout(io.StringIO()):run.collect(root)
            result=review.review(root)
            self.assertTrue(result['passed']);self.assertEqual(len(seen),len(set(seen)))
            natural=[v for v in result['effects'] if v['phase']=='natural']
            self.assertEqual(len(natural),0 if held else 6)
            if not held:
                self.assertEqual(len(result['model_authored_shared_versions']),9)
                self.assertEqual(len(result['peer_quote_adoptions']),1)
                self.assertEqual(result['peer_quote_adoptions'][0]['actor'],second)
                self.assertTrue(result['peer_quote_adoptions'][0]['different_request'])
                self.assertGreaterEqual(len(result['temporal_candidates']),5)
                self.assertEqual(sum(v['fresh_wave'] for v in result['temporal_candidates']),4)
                self.assertTrue(all(v['different_request'] for v in result['temporal_candidates']))
                later=[x for x in result['peer_body_exposures'] if x['actor'] not in (first,second)]
                self.assertEqual(len(later),4)
                self.assertTrue(all(x['file']['origin']=='reconciliation' for x in later))
                exports=export_atif.export(root);self.assertEqual(len(exports),8)
                self.assertTrue(all(v['native_continuity_passed'] for v in exports))
            else:self.assertEqual(result['collection_status'],'provider_hold')
            self.assertTrue(all(v['removed'] for v in run.load(root/'cleanup-summary.json')['owned_workstations']))


if __name__=='__main__':unittest.main(verbosity=2)
