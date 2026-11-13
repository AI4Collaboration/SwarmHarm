"""Review outputs distinguish service journals from Operations SQLite."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2 import (consolidation_review,data_region_review,engineering_localization_review,
                    finance_assets_review,finance_performance_review,finance_closure_review,
                    knowledge_digest_review,work_files)


from phase2.activity_report import production_review as activity_review
from phase2.editorial_brief import production_review as editorial_review
from phase2.build_record import production_review as build_review, target_production_review as target_review


class ServiceJournalScopeChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.registration={'phase2':{'assignments':{'job-northline':{'account':'Northline',
            'delivery_config':{'access':{'payables_workflow':'account-retirement'}}}}},
            'budget':{'max_actor_seconds':600,'max_batch_seconds':600}}
        self.world={'events':[]}
        self.world_patch=patch.object(work_files,'audit',return_value={});self.world_patch.start();self.addCleanup(self.world_patch.stop)

    def file(self,path,value):
        target=self.root/'natural'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(value)

    def check(self,result,action_key,scope):
        action=result[action_key];effect=result['collective_outcomes'][0]
        for row in (action,effect):
            self.assertTrue(row['operations_ledger_match']) # generic contract compatibility
            self.assertFalse(row['operations_ledger_applicable'])
            self.assertEqual(row['operations_ledger_scope'],'not_applicable')
            self.assertEqual(row['service_journal_scope'],scope)

    def test_file_service_reviewers(self):
        cases=[(data_region_review,'data-region','region_action','data_region'),
               (engineering_localization_review,'localization','localization_action','engineering_localization'),
               (finance_assets_review,'finance-assets','assets_action','finance_assets'),
               (finance_performance_review,'finance-performance','performance_action','finance_performance')]
        observed={'actions':[],'causal_actors':[],'outcomes':{}}
        for module,name,key,dependency in cases:
            with self.subTest(name=name):
                self.file(f'operator/{name}-service/operator/native-call-events.jsonl','')
                self.file(f'operator/{name}-observation.json',json.dumps({'mechanical_observation':observed}))
                with patch.object(getattr(module,dependency),'monitor',return_value=observed):
                    result=module.assess(self.root,self.registration,self.world)
                self.check(result,key,f'{name}-service/operator/native-call-events.jsonl')

    def test_consolidation(self):
        observed={'actual':{},'retained_actions':[],'causal_actors':[]}
        self.file('operator/consolidation-service/operator/native-call-events.jsonl','')
        self.file('operator/consolidation-observation.json',json.dumps({'mechanical_observation':observed}))
        with patch.object(consolidation_review,'monitor',return_value=observed):
            result=consolidation_review.assess(self.root,self.registration,self.world)
        self.check(result,'consolidation_action','consolidation-service/operator/native-call-events.jsonl')

    def test_activity_editorial_and_build_services(self):
        observed={'causal_actions':[],'outcomes':{},'publication_reads':[],
                  'mechanism_observed':False,'final':{},'corrected_final':{},'actual':{}}
        cases=[(activity_review,'activity-report','activity-mechanical-observation','activity_action','activity-report/events.jsonl','audit'),
               (editorial_review,'editorial-brief','editorial-mechanical-observation','editorial_action','editorial-brief/events.jsonl','audit'),
               (build_review,'build-check-service','build-mechanical-observation','build_record_action',
                'build-check-service/operator/native-call-events.jsonl; build-check-service/operator/business-events.jsonl','monitor'),
               (target_review,'build-target-service','build-target-observation','target_action',
                'build-target-service/operator/native-call-events.jsonl; build-target-service/operator/business-events.jsonl','monitor')]
        for module,name,observation,key,scope,dependency in cases:
            with self.subTest(name=name):
                (self.root/'natural/operator'/name).mkdir(parents=True,exist_ok=True)
                self.file(f'operator/{observation}.json',json.dumps({'mechanical_observation':observed}))
                with patch.object(module,dependency,return_value=observed):
                    result=module.assess(self.root,self.registration,self.world)
                self.check(result,key,scope)

    def test_payment_and_digest_protected_events(self):
        start='2026-11-01T00:00:00+00:00'
        payment={'retained_action_statuses_match':True,'read_snapshots_match':True,'missed_first_window':[]}
        self.file('activation.json',json.dumps({'activated_at':start}))
        self.file('operator/finance-closure-service/protected-events.jsonl',json.dumps({'result':{'started_at':start}})+'\n')
        self.file('operator/finance-closure-observation.json',json.dumps({'mechanical_observation':payment}))
        with patch.object(finance_closure_review,'inspect',return_value=payment):
            result=finance_closure_review.assess(self.root,self.registration,self.world)
        self.check(result,'closure_action','finance-closure-service/protected-events.jsonl')

        reserve=knowledge_digest_review.q.ACTIVATION_RESERVE
        info={'actor_budget_seconds':600,'batch_remaining_seconds':600,'reserve_seconds':reserve,'observation_limit_seconds':600-reserve}
        digest={'statuses_match':True,'reads_match':True,'full_results_match':True,'missed_first_window':[]}
        self.file('activation.json',json.dumps({'activated_at':start,'digest_observation_budget':info}))
        self.file('operator/knowledge-digest-service/protected-events.jsonl',json.dumps({'result':{'started_at':start,'observation_limit_seconds':600-reserve}})+'\n')
        self.file('operator/knowledge-digest-observation.json',json.dumps({'mechanical_observation':digest}))
        with patch.object(knowledge_digest_review,'inspect',return_value=digest), patch.object(knowledge_digest_review,'attribution_coverage',return_value={'attribution_supported':False}):
            result=knowledge_digest_review.assess(self.root,self.registration,self.world)
        self.check(result,'digest_action','knowledge-digest-service/protected-events.jsonl')


if __name__=='__main__':unittest.main()
