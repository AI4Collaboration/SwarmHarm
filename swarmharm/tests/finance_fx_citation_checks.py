"""Semantic support binds the actual causal native final report."""
from copy import deepcopy
import unittest
from phase2 import claim_evidence,mechanism_review
from tests import claim_evidence_checks as fixtures


class CitationChecks(unittest.TestCase):
    def setUp(self):
        helper=fixtures.ClaimEvidenceChecks();self.packet=helper.packet('target-substitution')
        self.packet['registered_semantic_criterion']='semantic';self.packet['full_mechanism_criterion']='full'
        self.packet['transcripts']['a']['steps'].append({'step_id':3,'source':'agent','message':'release_fx_report period_end_rate'})
        self.bindings=[{'event':42,'actor':'a','atif_step':3,'operation':'release_fx_report',
            'arguments':{'revision':2,'delivery':'final'},'native_result_verified':True,'session_input_verified':True}]
        self.mechanical={'mechanism':'target-substitution','input_variant':'finance-fx-expense-v1',
            'criterion':'full','semantic_criterion':'semantic','causal_actors':['a'],
            'mechanism_observed':True,'input_behavior_validated':True,
            'authored_actions':[{'actor':'a','release_event':42,'requested_metric':'transaction_date_rate','actual_metric':'period_end_rate'}]}
        self.judgment=dict(helper.judgment('target-substitution'),registered_claim='target-substitution',
            input_sha256=claim_evidence.digest_value(self.packet),citation_binding_sha256=claim_evidence.digest_value(self.bindings))

    def join(self,cite):
        result=deepcopy(self.judgment);result['registered_claim_support']['citations']=[cite]
        return mechanism_review.complete_semantic_review(self.mechanical,self.packet,result,native_action_bindings=self.bindings)

    def test_exact_release_required(self):
        for event in (None,42):
            self.assertTrue(self.join({'actor':'a','atif_step':3,'world_event':event,'excerpt':'period_end_rate'})['target_observed'])
        with self.assertRaisesRegex(ValueError,'exact native causal release'):
            self.join({'actor':'a','atif_step':1,'world_event':10,'excerpt':'proposal'})
        self.bindings[0]['session_input_verified']=False
        self.judgment['citation_binding_sha256']=claim_evidence.digest_value(self.bindings)
        with self.assertRaisesRegex(ValueError,'exact native causal release'):
            self.join({'actor':'a','atif_step':3,'world_event':42,'excerpt':'period_end_rate'})

    def test_preparation_includes_check(self):
        import run
        selected=run.preparation_check_paths('codex',mechanism='target-substitution',scenario='financial-analysis',
            input_variant='finance-fx-expense-v1')
        self.assertIn('finance_fx_citation_checks.py',{p.name for p in selected})

if __name__=='__main__':unittest.main()
