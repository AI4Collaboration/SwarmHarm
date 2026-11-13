"""Scheduled-store notices retain real shared changes and exclude proven peer-only metadata."""
import base64
from hashlib import sha256
from types import SimpleNamespace
import unittest
import run
from phase2 import delivery_retention, unified_delivery
from scripts.inspect_unified_input import build_preview

class ScheduledNotificationChecks(unittest.TestCase):
    def make_flow(self):
        manifest,_=build_preview('knowledge-work','availability',mechanism='work-lifecycle',input_variant='knowledge-scheduled-consumer-v1')
        plan=manifest['assignments'];actors=list(plan)
        flow=unified_delivery.Continuation(SimpleNamespace(events=[],operator=None,plan={a:{'start_group':0} for a in plan}),plan)
        flow.activate();return flow,actors

    def test_other_account_execution_is_not_relevant_but_unknown_fields_remain(self):
        flow,actors=self.make_flow();actor,peer=actors[:2]
        before=flow.activity_signal(actor)
        self.assertEqual(flow.call(peer,1,'execute_dispatch',{'revision':1})['status'],200)
        after=flow.activity_signal(actor)
        self.assertEqual(before['revision'],after['revision'])
        own=flow._progress_view(flow._desk(actor));one=flow._scheduled_notice_projection(own,flow.plan[actor]['account'])
        own['new_unknown_field']={'some':'change'}
        two=flow._scheduled_notice_projection(own,flow.plan[actor]['account'])
        self.assertNotEqual(unified_delivery.digest(one),unified_delivery.digest(two))

    def test_global_check_summaries_do_not_hide_the_own_status(self):
        flow,actors=self.make_flow();actor,peer=actors[:2];account=flow.plan[actor]['account']
        before=flow.activity_signal(actor);original=flow._desk(actor)
        self.assertIn('checked_revisions',original['edition_check'])
        self.assertNotIn('checked_revisions',flow._progress_view(original)['edition_check'])
        flow.plans[peer]['revision']+=1
        self.assertNotEqual(original['edition_check']['checked_revisions'],flow._desk(actor)['edition_check']['checked_revisions'])
        self.assertEqual(before['revision'],flow.activity_signal(actor)['revision'])
        flow.call(actor,1,'execute_dispatch',{'revision':1})
        projected=flow._scheduled_notice_projection(flow._progress_view(flow._desk(actor)),account)['edition_check']
        self.assertEqual(projected['accounts'][account]['state'],'ready')
        self.assertEqual(set(projected['accounts'][account]['completed_items']),set(unified_delivery.ITEMS))
        self.assertNotEqual(before['revision'],flow.activity_signal(actor)['revision'])

    def test_aggregate_policy_only_removed_when_individual_checks_exist(self):
        flow,actors=self.make_flow();account=flow.plan[actors[0]]['account'];peer=flow.plan[actors[1]]['account']
        example={'edition_check':{'state':'incomplete','policy_checks':{'passed':1,'total':2},
                 'accounts':{account:{'state':'ready','policy_checks':{'passed':1,'total':1}},
                             peer:{'state':'incomplete','policy_checks':{'passed':0,'total':1}}}}}
        projected=flow._scheduled_notice_projection(example,account)['edition_check']
        self.assertNotIn('state',projected);self.assertNotIn('policy_checks',projected)
        self.assertEqual(projected['accounts'][account]['policy_checks'],{'passed':1,'total':1})
        example['edition_check']['accounts'][peer].pop('policy_checks')
        projected=flow._scheduled_notice_projection(example,account)['edition_check']
        self.assertIn('policy_checks',projected)
        example['edition_check']['accounts'][account].pop('state')
        projected=flow._scheduled_notice_projection(example,account)['edition_check']
        self.assertEqual(projected,example['edition_check'])

    def test_real_store_change_notice_and_exact_read_acknowledges_it(self):
        flow,actors=self.make_flow();actor,peer=actors[:2];before=flow.activity_signal(actor)
        self.assertEqual(flow.call(peer,1,delivery_retention.CLEAN_ONE,{'snapshot':'OPS-01'})['removed'],['OPS-01'])
        after=flow.activity_signal(actor);self.assertNotEqual(before['revision'],after['revision'])
        self.assertEqual(run.work_notice(extension=flow,actor=actor,check={'complete':False},signal=after,delivered=before)[1],'relevant_platform_change')
        trigger=run.notification_trigger(after,before,flow.world.events)
        self.assertIn('reporting_store',trigger['component_changes'])
        self.assertEqual(trigger['source_event_candidates'][-1]['operation'],delivery_retention.CLEAN_ONE)
        result=flow.call(actor,2,delivery_retention.READ,{});observed=flow.activity_signal(actor)
        received=run.acknowledge_tool_activity(flow,delivery_retention.READ,result,observed,before,after,actor=actor)
        self.assertEqual(run.work_notice(extension=flow,actor=actor,check={'complete':False},signal=observed,delivered=received),(None,None))
        self.assertTrue(flow.call(peer,3,delivery_retention.RESTORE,{'snapshot':'OPS-01'})['changed'])
        changed=flow.activity_signal(actor)
        self.assertEqual(run.work_notice(extension=flow,actor=actor,check={'complete':False},signal=changed,delivered=received)[1],'relevant_platform_change')

    def test_new_store_change_after_read_is_not_acknowledged(self):
        flow,actors=self.make_flow();actor,peer=actors[:2];delivered=flow.activity_signal(actor)
        flow.call(peer,1,delivery_retention.CLEAN_ONE,{'snapshot':'OPS-01'});before=flow.activity_signal(actor)
        result=flow.call(actor,2,delivery_retention.READ,{})
        flow.call(peer,3,delivery_retention.CLEAN_ONE,{'snapshot':'OPS-02'});after=flow.activity_signal(actor)
        received=run.acknowledge_tool_activity(flow,delivery_retention.READ,result,after,delivered,before,actor=actor)
        self.assertNotEqual(received['calendar_revision'],after['calendar_revision'])
        self.assertEqual(run.work_notice(extension=flow,actor=actor,check={'complete':False},signal=after,delivered=received)[1],'relevant_platform_change')

    def test_full_desk_response_acknowledges_same_projection(self):
        flow,actors=self.make_flow();actor,peer=actors[:2];delivered=flow.activity_signal(actor)
        flow.call(peer,1,delivery_retention.CLEAN_ONE,{'snapshot':'OPS-01'});before=flow.activity_signal(actor)
        result=flow.call(actor,2,'delivery_desk',{});after=flow.activity_signal(actor)
        received=run.acknowledge_tool_activity(flow,'delivery_desk',result,after,delivered,before,actor=actor)
        self.assertEqual(received['revision'],after['revision'])

    def test_shared_message_remains_visible(self):
        flow,actors=self.make_flow();actor,peer=actors[:2];before=flow.activity_signal(actor)
        path='/registry/reporting/cache/note.md';flow.world.shared[path]={'path':path,'author':peer,'sha256':sha256(b'Actual peer note').hexdigest(),'data':base64.b64encode(b'Actual peer note').decode()}
        after=flow.activity_signal(actor)
        self.assertNotEqual(before['revision'],after['revision'])
        self.assertTrue(run.notification_trigger(after,before,flow.world.events)['peer_record_trigger'])
        self.assertEqual(run.work_notice(extension=flow,actor=actor,check={'complete':False},signal=after,delivered=before)[1],'relevant_platform_change')
        read=run.acknowledge_observed_activity(after,before,{(path,sha256(b'Actual peer note').hexdigest())})
        self.assertEqual(run.work_notice(extension=flow,actor=actor,check={'complete':False},signal=after,delivered=read),(None,None))

    def test_actual_consumer_completion_is_a_new_shared_state(self):
        from datetime import datetime,timedelta,timezone
        flow,actors=self.make_flow();actor=actors[0]
        # Recreate a controllable clock before activation in a new flow.
        manifest,_=build_preview('knowledge-work','availability',mechanism='work-lifecycle',input_variant='knowledge-scheduled-consumer-v1')
        plan=manifest['assignments'];flow=unified_delivery.Continuation(SimpleNamespace(events=[],operator=None,plan={a:{'start_group':0} for a in plan}),plan)
        class Clock:
            seconds=0.0
            start=datetime(2026,1,1,tzinfo=timezone.utc)
            def monotonic(self):return self.seconds
            def wall(self):return self.start+timedelta(seconds=self.seconds)
        c=Clock();flow.retention.clock=c.monotonic;flow.retention.wall=c.wall;flow.activate();before=flow.activity_signal(actor)
        c.seconds=flow.retention.delay_seconds;self.assertTrue(flow.advance_business_time(c.seconds))
        after=flow.activity_signal(actor)
        self.assertEqual(run.work_notice(extension=flow,actor=actor,check={'complete':False},signal=after,delivered=before)[1],'relevant_platform_change')
        self.assertIn('operations_consumer_completed',[row['operation'] for row in run.notification_trigger(after,before,flow.world.events)['source_event_candidates']])

    def test_other_scheduled_domain_keeps_existing_projection(self):
        manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        plan=manifest['assignments'];actor=next(iter(plan));flow=unified_delivery.Continuation(SimpleNamespace(events=[],operator=None,plan={a:{'start_group':0} for a in plan}),plan)
        self.assertFalse(flow._scheduled_notice_projection_enabled())
        self.assertNotIn('event_cursor',flow.activity_signal(actor))
        desk=flow._progress_view(flow._desk(actor))
        self.assertEqual(flow._scheduled_notice_projection(desk,plan[actor]['account']),desk)

    def test_unconfirmed_component_is_marked_unclassified(self):
        before={'revision':'old','calendar_revision':'a','calendar_components':{'unknown':'a'},'event_cursor':1}
        after={'revision':'new','calendar_revision':'b','calendar_components':{'unknown':'b'},'event_cursor':2}
        trigger=run.notification_trigger(after,before,[{'id':2,'actor':'peer','operation':'unknown_change'}])
        self.assertEqual(trigger['unclassified_components'],['unknown'])
        self.assertEqual(trigger['source_event_candidates'][0]['id'],2)
        self.assertIn('not asserted causal',trigger['source_scope'])

    def test_own_action_receipt_does_not_repeat_itself(self):
        flow,actors=self.make_flow();actor=actors[0];before=flow.activity_signal(actor)
        result=flow.call(actor,1,delivery_retention.CLEAN_ONE,{'snapshot':'OPS-01'});after=flow.activity_signal(actor)
        received=run.acknowledge_tool_activity(flow,delivery_retention.CLEAN_ONE,result,after,before,before,actor=actor)
        self.assertEqual(received['revision'],after['revision'])

    def test_combined_exact_read_suppresses_duplicate_store_notice(self):
        flow,actors=self.make_flow();actor,peer=actors[:2];filing={'revision':'f','relevant_cross_job_records':0}
        signal=lambda:run.combined_activity_signal(filing,flow.activity_signal(actor),True)
        delivered=signal();flow.call(peer,1,delivery_retention.CLEAN_ONE,{'snapshot':'OPS-01'})
        before=signal();result=flow.call(actor,2,delivery_retention.READ,{});after=signal()
        received=run.acknowledge_tool_activity(flow,delivery_retention.READ,result,after,delivered,before,actor=actor)
        self.assertEqual(run.work_notice(extension=flow,actor=actor,check={'complete':False},signal=after,delivered=received),(None,None))

    def test_new_check_is_selected_for_only_knowledge_variant(self):
        for domain,variant,expected in [('knowledge-work','knowledge-scheduled-consumer-v1',True),
                                        ('data-analysis','data-scheduled-consumer-v1',False)]:
            paths=run.preparation_check_paths('codex',mechanism='work-lifecycle',scenario=domain,input_variant=variant)
            self.assertEqual('scheduled_notification_checks.py' in {p.name for p in paths},expected)

    def test_combined_signal_retains_auditable_cursor(self):
        flow,actors=self.make_flow();a=actors[0];filing={'revision':'f','relevant_cross_job_records':0}
        signal=run.combined_activity_signal(filing,flow.activity_signal(a),True)
        self.assertEqual(signal['event_cursor'],flow.activity_signal(a)['event_cursor'])

if __name__=='__main__':unittest.main()
