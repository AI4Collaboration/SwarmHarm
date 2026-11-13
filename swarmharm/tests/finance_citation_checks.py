"""Finance action citations require their exact native result and ATIF step."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import claim_evidence, communication_evidence, mechanism_review
from scripts.judge_unified_transcript import citation_events
from scripts.reprocess_finance_judgment import separate_directory
from tests import claim_evidence_checks as evidence_fixtures


class FinanceCitationChecks(unittest.TestCase):
    def setUp(self):
        helper=evidence_fixtures.ClaimEvidenceChecks()
        self.packet=helper.packet('work-lifecycle')
        self.packet['registered_semantic_criterion']='semantic'
        self.packet['full_mechanism_criterion']='full'
        self.packet['transcripts']['a']['steps'].append({
            'step_id':3,'source':'agent','message':'cancel_payment_order INV-1'})
        self.packet['transcripts']['a']['steps'].append({
            'step_id':4,'source':'agent','message':'read_payment_account INV-1'})
        self.mechanical={'mechanism':'work-lifecycle','input_variant':'finance-account-retirement-v1',
            'criterion':'full','semantic_criterion':'semantic','causal_actors':['a'],
            'mechanism_observed':True,'input_behavior_validated':True,
            'authored_actions':[{'event':42,'actor':'a','operation':'cancel_payment_order'},
                                {'event':43,'actor':'b','operation':'cancel_payment_order'},
                                {'event':44,'actor':'a','operation':'read_payment_account'}]}
        self.bindings=[{'event':42,'actor':'a','atif_step':3,'operation':'cancel_payment_order',
                        'arguments':{'invoice_id':'INV-1','account':'current'},
                        'native_result_verified':True,'session_input_verified':True},
                       {'event':44,'actor':'a','atif_step':4,'operation':'read_payment_account',
                        'arguments':{},'native_result_verified':True,'session_input_verified':True}]
        self.judgment=dict(helper.judgment('work-lifecycle'),registered_claim='work-lifecycle',
            input_sha256=claim_evidence.digest_value(self.packet),
            citation_binding_sha256=claim_evidence.digest_value(self.bindings))

    def join(self,citation,bindings=None):
        value=deepcopy(self.judgment);value['registered_claim_support']['citations']=[citation]
        bindings=self.bindings if bindings is None else bindings
        value['citation_binding_sha256']=claim_evidence.digest_value(bindings)
        return mechanism_review.complete_semantic_review(self.mechanical,self.packet,value,
                                                         native_action_bindings=bindings)

    def test_atif_only_action_is_selected_and_exactly_bound(self):
        for event in (None,42):
            citation={'actor':'a','atif_step':3,'world_event':event,'excerpt':'cancel_payment_order'}
            payload=deepcopy(self.judgment);payload['registered_claim_support']['citations']=[citation]
            self.assertEqual(citation_events(payload,self.mechanical),{10,11,42})
            self.assertTrue(self.join(citation)['target_observed'])

    def test_noncausal_step_or_unverified_result_cannot_pass(self):
        citation={'actor':'a','atif_step':4,'world_event':None,'excerpt':'read_payment_account'}
        with self.assertRaisesRegex(ValueError,'exact native causal action'):
            self.join(citation)
        citation={'actor':'a','atif_step':3,'world_event':44,'excerpt':'cancel_payment_order'}
        with self.assertRaises(ValueError):
            self.join(citation)
        citation={'actor':'a','atif_step':3,'world_event':None,'excerpt':'cancel_payment_order'}
        for field in ('native_result_verified','session_input_verified'):
            bindings=deepcopy(self.bindings);bindings[0][field]=False
            with self.assertRaisesRegex(ValueError,'native delivery|exact native causal action'):
                self.join(citation,bindings)

    def test_real_result_and_following_request_are_bound(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);(root/'registration.json').write_text(json.dumps({'harness':{'kind':'codex'}}))
            folder=root/'natural/a';(folder/'trace').mkdir(parents=True);(folder/'agent').mkdir()
            args={'invoice_id':'INV-1','account':'current'};result={'status':200,'invoice_id':'INV-1','account':'current'}
            event={'id':42,'actor':'a','operation':'cancel_payment_order','arguments':args,'result':result}
            record={'event_id':42,'call_id':'one','name':'cancel_payment_order','arguments':args,'result':result}
            (folder/'trace/0001-tool-0001.json').write_text(json.dumps(record))
            (folder/'trace/0002.request.json').write_text(json.dumps({'input':[
                {'type':'function_call_output','call_id':'one','output':json.dumps(result)}]}))
            (folder/'agent/trajectory.json').write_text(json.dumps({'steps':[{'step_id':3,
                'tool_calls':[{'tool_call_id':'one'}],
                'extra':{'tool_result_delivery':{'one':{'sdk_delivery_verified':True}}}}]}))
            bound=list(communication_evidence.bind_events(root,{'events':[event]},['a'],{42},refresh_atif=False).values())
            citation={'actor':'a','atif_step':3,'world_event':None,'excerpt':'cancel_payment_order'}
            self.assertTrue(self.join(citation,bound)['target_observed'])
            record['result']={'status':409}
            (folder/'trace/0001-tool-0001.json').write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError,'differs from native'):
                communication_evidence.bind_events(root,{'events':[event]},['a'],{42},refresh_atif=False)

    def test_registered_preparation_selects_the_citation_check(self):
        import run
        paths=run.preparation_check_paths('codex',mechanism='work-lifecycle',
            scenario='financial-analysis',input_variant='finance-account-retirement-v1')
        self.assertIn('finance_citation_checks.py',{path.name for path in paths})

    def test_rereview_requires_a_new_separate_directory(self):
        with TemporaryDirectory() as directory:
            parent=Path(directory).resolve();original=parent/'original';original.mkdir()
            for bad in (original,original/'nested',parent):
                with self.assertRaises(ValueError):separate_directory(original,bad)
            occupied=parent/'occupied';occupied.mkdir()
            with self.assertRaises(FileExistsError):separate_directory(original,occupied)
            separate_directory(original,parent/'new-review')


if __name__=='__main__':unittest.main()
