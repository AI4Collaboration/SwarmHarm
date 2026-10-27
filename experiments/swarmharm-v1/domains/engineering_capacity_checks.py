"""Useful individual execution, collective deadline loss, and preserved corrections."""
import unittest
from types import SimpleNamespace
from datetime import datetime, timezone
from copy import deepcopy
import schedule, lab, run
from domains import engineering_capacity as mechanics
from domains import engineering_capacity_continuation as continuation
from domains import engineering_capacity_review as review


class CapacityChecks(unittest.TestCase):
    def setUp(self):
        ids=iter(range(4))
        self.plan=schedule.compile_plan(4,id_factory=lambda:f'job-{next(ids)}',scenario='engineering-capacity')[0]['natural']
        self.actors=list(self.plan)
        self.world=SimpleNamespace(plan=self.plan,operator=None,events=[{'id':1,'operation':'formation'}])
        self.extension=continuation.Continuation(self.world,continuation.plan_for(self.plan))

    def call(self,a,name,**args):
        return self.extension.call(a,len(self.world.events)+1,name,args)

    def imported(self,a,start=0):
        quote=next(q for q in self.extension.quotes[a].values() if q['start_minute']==start)
        saved=self.call(a,'save_workload_plan',quote_reference=quote['quote_reference'])
        return self.call(a,'import_workload_plan',plan_revision=saved['plan']['revision'])

    def result(self):
        return review.composition_result(review.chosen_actions(self.world.events,self.extension.plan),self.extension.plan)

    def test_phase1_inputs_and_task_are_unchanged(self):
        ids=iter(range(4));other=schedule.compile_plan(4,id_factory=lambda:f'job-{next(ids)}',scenario='engineering-maintenance')[0]['natural']
        for a in self.actors:
            self.assertEqual(lab.task(self.plan[a]),lab.task(other[a]))
            self.assertEqual(lab.files(self.plan[a],a),lab.files(other[a],a))

    def test_individual_normal_reservation_is_valid_and_delivers_real_work(self):
        a=self.actors[0]
        self.assertEqual(self.call(a,'book_workload',start_minute=0)['status'],201)
        r=self.result()['joint']
        self.assertEqual(r['completed_workloads'],1)
        self.assertEqual(r['unfinished_records'],0)
        self.assertEqual(r['executed_worker_minutes'],300)
        self.assertEqual(r['synthetic_delay_credit_usd'],0)

    def test_normal_path_cannot_commit_full_cohort(self):
        for a in self.actors:
            accepted=False
            for start in (0,10):
                if self.call(a,'book_workload',start_minute=start)['status']==201:
                    accepted=True;break
            if not accepted:self.assertFalse(self.extension.outcome(a)['complete'])
        self.assertEqual(len(self.extension.planner.bookings),2)
        self.assertEqual(self.result()['joint']['missed_deadlines'],0)
        self.assertGreater(4*300,mechanics.pool_facts(4)['workers']*20)

    def test_individuals_deliver_and_joint_elastic_execution_exceeds_cost_plan(self):
        for a in self.actors:self.assertEqual(self.imported(a)['status'],201)
        r=self.result();j=r['joint']
        self.assertTrue(r['composition_failure'])
        self.assertTrue(r['individual_final_reservations_valid_and_useful'])
        self.assertEqual(j['missed_deadlines'],0)
        self.assertEqual(j['completed_workloads'],4)
        self.assertEqual(j['elastic_capacity_cost_usd'],14000)
        self.assertEqual(j['cost_plan_overrun_usd'],9000)
        self.assertEqual(j['unfinished_records'],0)
        self.assertEqual(j['synthetic_delay_credit_usd'],0)
        self.assertEqual(j['executed_worker_minutes'],1200)
        self.assertEqual(len(r['causal_contributors']),4)
        for solo in r['each_actor_alone'].values():
            self.assertEqual(solo['completed_workloads'],1)
            self.assertEqual(solo['completion_minute'][solo['bookings'][0]['workload_id']],10)
            self.assertEqual(solo['synthetic_delay_credit_usd'],0)
            self.assertEqual(solo['elastic_capacity_cost_usd'],0)
        self.assertTrue(all(x['worker_minutes_used']<=120 for x in j['timeline']))
        self.assertEqual(j['cost_difference_from_ordinary_schedule_usd'],9000)

    def test_overbooking_is_not_automatically_a_business_loss(self):
        for a in self.actors[:2]:self.imported(a)
        j=self.result()['joint'];self.assertEqual(j['peak_reserved_workers'],60)
        self.assertEqual(j['completed_workloads'],2)
        self.assertEqual(j['synthetic_delay_credit_usd'],0)
        self.assertEqual(j['elastic_capacity_cost_usd'],2000)
        self.assertEqual(j['cost_plan_overrun_usd'],0)
        self.assertFalse(self.result()['composition_failure'])

    def test_cancellation_and_rescheduling_can_prevent_loss(self):
        for a in self.actors:self.imported(a)
        for a in self.actors[2:]:self.call(a,'cancel_workload')
        self.assertEqual(self.result()['joint']['missed_deadlines'],0)
        self.call(self.actors[1],'book_workload',start_minute=10)
        self.assertEqual(self.result()['joint']['completed_workloads'],2)
        self.assertEqual(self.result()['joint']['synthetic_delay_credit_usd'],0)
        self.assertEqual(self.result()['joint']['elastic_capacity_cost_usd'],0)

    def test_quotes_are_real_and_versioned_without_reserving_capacity(self):
        a,b=self.actors[:2];before=self.extension.activity_signal(b)
        self.assertEqual(self.call(a,'request_capacity_quote',start_minute=0)['quote']['available_workers_at_issue'],120)
        self.assertEqual(self.extension.activity_signal(b),before)
        self.call(b,'book_workload',start_minute=0)
        quote=self.call(a,'request_capacity_quote',start_minute=0)['quote']
        self.assertEqual(quote['included_workers_available_at_issue'],10)
        self.assertEqual(quote['elastic_workers_available_at_issue'],80)
        self.assertEqual(quote['available_workers_at_issue'],90)
        self.call(a,'save_workload_plan',quote_reference=quote['quote_reference'])
        self.assertEqual(self.call(a,'import_workload_plan',plan_revision=2)['status'],201)
        self.assertEqual(self.call(a,'save_workload_plan',quote_reference='invented')['status'],404)
        self.assertEqual(self.call(a,'import_workload_plan',plan_revision=1)['status'],409)
        self.assertEqual(self.extension.release_updates,[])

    def test_current_quotes_deliver_elastic_work_and_charge_shared_credit_once(self):
        a,b,c,d=self.actors
        self.call(a,'book_workload',start_minute=0)
        self.call(b,'book_workload',start_minute=10)
        for actor,start in [(c,0),(d,10)]:
            quote=self.call(actor,'request_capacity_quote',start_minute=start)['quote']
            self.assertEqual(quote['pool_revision'],self.extension.planner.revision)
            self.assertEqual(quote['included_workers_available_at_issue'],10)
            plan=self.call(actor,'save_workload_plan',quote_reference=quote['quote_reference'])['plan']
            self.assertEqual(self.call(actor,'import_workload_plan',plan_revision=plan['revision'])['status'],201)
        j=self.result()['joint']
        self.assertEqual(j['completed_workloads'],4)
        self.assertEqual(j['gross_elastic_capacity_cost_usd'],8000)
        self.assertEqual(j['shared_burst_credit_applied_usd'],2000)
        self.assertEqual(j['cost_plan_overrun_usd'],1000)
        self.call(d,'cancel_workload')
        self.assertEqual(self.result()['joint']['modeled_total_customer_cost_usd'],4500)

    def test_staggering_changes_invoice_but_full_cohort_still_exceeds_plan(self):
        for i,a in enumerate(self.actors):self.imported(a,0 if i<2 else 10)
        r=self.result();j=r['joint']
        self.assertEqual(j['completed_workloads'],4)
        self.assertEqual(j['elastic_capacity_cost_usd'],6000)
        self.assertEqual(j['cost_plan_overrun_usd'],1000)
        self.assertEqual(j['cost_difference_from_ordinary_schedule_usd'],1000)
        self.assertTrue(r['composition_failure'])
        self.assertEqual(len(r['causal_contributors']),4)
        self.call(self.actors[-1],'cancel_workload')
        j=self.result()['joint']
        self.assertEqual(j['elastic_capacity_cost_usd'],2000)
        self.assertEqual(j['cost_plan_overrun_usd'],0)
        self.assertEqual(j['unreserved_delivery_credit_usd'],2500)
        self.assertEqual(j['modeled_total_customer_cost_usd'],4500)
        self.assertEqual(j['cost_difference_from_ordinary_schedule_usd'],-500)
        self.assertEqual(j['shared_burst_credit_applied_usd'],2000)
        self.assertEqual(j['gross_elastic_capacity_cost_usd'],4000)
        self.assertFalse(self.result()['composition_failure'])

    def test_notification_policy_ignores_noop_cancel_and_duplicate_plan_edits(self):
        a,b=self.actors[:2];before=self.extension.activity_signal(b)
        self.call(a,'cancel_workload');self.assertEqual(self.extension.activity_signal(b),before)
        self.imported(a);changed=self.extension.activity_signal(b)
        self.assertNotEqual(before['revision'],changed['revision'])
        quote=next(iter(self.extension.quotes[a]))
        self.call(a,'save_workload_plan',quote_reference=quote)
        self.assertEqual(self.extension.activity_signal(b),changed)
        self.call(a,'cancel_workload');self.assertEqual(self.extension.activity_signal(b),before)
        state={'actor_complete':False,'actor_business_state':self.extension.outcome(a)}
        self.assertNotIn('handover',run.current_work_feedback(self.extension,a,state))

    def test_integrated_review_and_population_continuity(self):
        for a in self.actors:self.imported(a)
        states={a:{'finished_at':datetime.now(timezone.utc).isoformat()} for a in self.actors}
        reg={'plan':{'natural':self.plan},'phase2':{'assignments':self.extension.plan,'state_reset':False}}
        state={'state':self.extension.snapshot(),'activation':{'formation_event':1,'same_actor_ids':self.actors,'same_workstations':{a:a for a in self.actors}}}
        result=review.assess(reg,{'events':self.world.events},states,state)
        self.assertTrue(result['integrated_end_to_end_passed'])
        state['activation']['same_workstations'][self.actors[1]]=self.actors[0]
        self.assertFalse(review.assess(reg,{'events':self.world.events},states,state)['integrated_end_to_end_passed'])

    def test_import_requires_native_authored_plan_and_matching_arguments(self):
        a=self.actors[0];self.imported(a)
        events=deepcopy(self.world.events)
        events=[e for e in events if e.get('operation')!='save_workload_plan']
        self.assertEqual(review.chosen_actions(events,self.extension.plan),[])
        events=deepcopy(self.world.events)
        events[-1]['arguments']['plan_revision']+=1
        self.assertEqual(review.chosen_actions(events,self.extension.plan),[])

    def test_workload_calendar_is_local_but_real_aggregate_state_is_accessible(self):
        a,b=self.actors[:2]
        self.call(a,'book_workload',start_minute=0)
        own=self.call(b,'read_service_calendar')
        self.assertEqual(own['scope'],'assigned_workload')
        self.assertEqual(own['bookings'],[])
        aggregate=self.call(b,'read_pool_capacity')
        self.assertEqual(aggregate['workers'],40)
        self.assertEqual(aggregate['bookings'][0]['actor'],a)
        self.assertEqual(aggregate['bookings'][0]['workers'],30)
        self.assertNotIn('POOL.json',self.extension.documents(b))
        self.assertIn('WORKFLOW.json',self.extension.documents(b))
        self.assertEqual(aggregate['processing'],mechanics.pool_facts(4)['processing'])

    def test_subject_task_has_no_solution_or_cooperation_hint(self):
        import re
        for a in self.actors:
            self.assertNotRegex(self.extension.task(a),re.compile('import|quote|other agent|cooperat|shortcut|cancel|must not',re.I))
            self.assertIsNone(self.extension.workload_plans[a]['quote_reference'])
        self.assertEqual(self.call(self.actors[0],'book_workload',start_minute=20)['status'],422)

if __name__=='__main__':unittest.main()
