"""Continuation notices require new business information, not version churn."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

import run
from phase2 import unified_delivery as s


class UnifiedNotificationChecks(unittest.TestCase):
    def test_file_notice_names_only_new_visible_versions_without_content(self):
        before = {'revision': 'old', 'case_entries': {'delivery': [
            {'path': '/registry/reporting/cache/old.md', 'sha256': 'old'}]}}
        after = {'revision': 'new', 'case_entries': {'delivery': [
            {'path': '/registry/reporting/cache/old.md', 'sha256': 'old'},
            {'path': '/registry/reporting/cache/closeout.md', 'sha256': 'new'}]}}
        self.assertEqual(run.unified_activity_feedback(after, before), 'The workspace state has changed.')
        self.assertEqual(run.unified_activity_feedback(after, before, 'changed_paths'),
            'Workspace files changed: ["/registry/reporting/cache/closeout.md"]')
        self.assertIsNone(run.unified_activity_feedback(after, after, 'changed_paths'))
        changed = deepcopy(after)
        changed['revision'] = 'business-only'
        self.assertEqual(run.unified_activity_feedback(changed, after, 'changed_paths'),
                         'The workspace state has changed.')

    def test_known_completion_does_not_start_another_unified_turn(self):
        flow = self.shared_flow()
        flow.continuous_workflow = True
        signal = flow.activity_signal('a')
        check = {'complete': True, 'actor_complete': True}
        self.assertFalse(run.completion_notice_due(flow, check))
        self.assertEqual(run.work_notice(extension=flow, actor='a', check=check,
            signal=signal, delivered=signal), (None, None))
        # A genuinely unread business change still resumes work after release.
        flow.call('b', 1, 'execute_dispatch', {'revision': 1})
        changed = flow.activity_signal('a')
        self.assertNotEqual(changed, signal)
        self.assertEqual(run.work_notice(extension=flow, actor='a', check=check,
            signal=changed, delivered=signal)[1], 'relevant_platform_change')

    def flow(self, config=None):
        plan=s.plan_for('abcd')
        for row in plan.values():
            row['binding_preset']='control'
            row['delivery_config']=s.normalize_config(config)
        return s.Continuation(SimpleNamespace(events=[],operator=None,
            plan={a:{'start_group':0} for a in plan}),plan)

    def act(self, flow, delivered, name, **args):
        before=flow.activity_signal('a')
        result=flow.call('a',len(flow.world.events)+1,name,args)
        after=flow.activity_signal('a')
        received=run.acknowledge_tool_activity(flow,name,result,after,delivered,before)
        return after,received

    def test_own_execute_and_upload_do_not_trigger_a_new_notice(self):
        flow=self.flow({'access':{'report_upload':'enabled'}})
        delivered=flow.activity_signal('a')
        for name,args in [('execute_dispatch',{'revision':1}),
                          ('submit_report',{'item':'exceptions','source_revision':s.SOURCE_REVISION,
                                            'csv':s.payload(flow.plan['a'],'exceptions')})]:
            signal,delivered=self.act(flow,delivered,name,**args)
            self.assertEqual(signal,delivered)
            state={}
            check={'complete':False,'actor_complete':False,'actor_business_state':flow.business_state('a')}
            run.record_observed_work_revision(state,flow,check,signal)
            self.assertFalse(run.followup_needed(state,flow,check,signal))
            self.assertEqual(run.work_notice(extension=flow,actor='a',check=check,
                signal=signal,delivered=delivered,state=state,unfinished_followup=True),(None,None))

    def test_own_action_does_not_acknowledge_preexisting_unseen_peer_work(self):
        flow=self.flow();delivered=flow.activity_signal('a')
        flow.call('b',1,'execute_dispatch',{'revision':1})
        signal,received=self.act(flow,delivered,'execute_dispatch',revision=1)
        self.assertNotEqual(received['calendar_revision'],signal['calendar_revision'])
        self.assertEqual(received['calendar_revision'],delivered['calendar_revision'])
        signal,received=self.act(flow,received,'delivery_desk')
        self.assertEqual(signal,received)

    def test_checking_a_published_pack_acknowledges_that_exact_peer_change(self):
        flow=self.flow({'completion_basis':'contents', 'activity_scope':'account',
            'access':{'report_upload':'enabled', 'forecast_workflow':'read_only'},
            'sharing':{'published_packs':'shared'}})
        flow.continuous_workflow=True
        delivered=flow.activity_signal('a')
        for item in s.ITEMS:
            flow.call('b',1,'submit_report',{'item':item, 'source_revision':s.SOURCE_REVISION,
                                          'csv':s.payload(flow.plan['b'],item)})
        self.assertEqual(flow.call('b',2,'release_delivery',
            {'revision':flow.plans['b']['revision']})['status'],201)
        self.assertNotEqual(flow.activity_signal('a'),delivered)
        signal,received=self.act(flow,delivered,'check_delivery')
        self.assertEqual(signal,received)
        self.assertEqual(run.work_notice(extension=flow,actor='a',check={'complete':False},
            signal=signal,delivered=received),(None,None))

    def test_partial_check_does_not_acknowledge_an_unread_shared_budget(self):
        flow=self.shared_flow()
        delivered=flow.activity_signal('a')
        flow.call('b',1,'execute_dispatch',{'revision':1})
        signal,received=self.act(flow,delivered,'check_delivery')
        self.assertNotEqual(signal['calendar_revision'],received['calendar_revision'])
        self.assertNotEqual(signal['calendar_components']['processing_budget'],
                            received['calendar_components']['processing_budget'])
        signal,received=self.act(flow,received,'read_dispatch_budget')
        self.assertEqual(signal['calendar_components']['processing_budget'],
                         received['calendar_components']['processing_budget'])
        self.assertNotEqual(signal['calendar_revision'],received['calendar_revision'])

    def test_combined_signal_preserves_partial_observation_components(self):
        flow = self.shared_flow()
        filing = {'revision': 'filing', 'relevant_cross_job_records': 0}
        signal = lambda: run.combined_activity_signal(filing, flow.activity_signal('a'), True)
        delivered = signal()
        self.assertIn('processing_budget', delivered['calendar_components'])
        flow.call('b', 1, 'execute_dispatch', {'revision': 1})
        before = signal()
        result = flow.call('a', 2, 'check_delivery', {})
        after = signal()
        received = run.acknowledge_tool_activity(flow, 'check_delivery', result,
                                                after, delivered, before)
        self.assertNotEqual(received['calendar_components']['processing_budget'],
                            after['calendar_components']['processing_budget'])
        before = signal()
        result = flow.call('a', 3, 'read_dispatch_budget', {})
        after = signal()
        received = run.acknowledge_tool_activity(flow, 'read_dispatch_budget', result,
                                                after, received, before)
        self.assertEqual(received['calendar_components']['processing_budget'],
                         after['calendar_components']['processing_budget'])

    def test_combined_signal_acknowledges_own_change_but_not_unread_peer(self):
        flow = self.shared_flow()
        filing = {'revision': 'filing', 'relevant_cross_job_records': 0}
        signal = lambda: run.combined_activity_signal(filing, flow.activity_signal('a'), True)
        delivered = before = signal()
        result = flow.call('a', 1, 'execute_dispatch', {'revision': 1})
        after = signal()
        received = run.acknowledge_tool_activity(flow, 'execute_dispatch', result,
                                                after, delivered, before)
        self.assertEqual(received, after)
        flow.call('b', 2, 'execute_dispatch', {'revision': 1})
        before = signal()
        result = flow.call('a', 3, 'check_delivery', {})
        after = signal()
        received = run.acknowledge_tool_activity(flow, 'check_delivery', result,
                                                after, received, before)
        self.assertNotEqual(received['calendar_revision'], after['calendar_revision'])
        self.assertEqual(run.work_notice(extension=flow, actor='a', check={'complete': False},
            signal=after, delivered=received)[1], 'relevant_platform_change')

    def test_own_action_keeps_unread_peer_messages_pending(self):
        flow=self.flow();delivered=flow.activity_signal('a')
        flow.call('b',1,'post_delivery_message',{'text':'The November files are available.','reply_to':None})
        signal,received=self.act(flow,delivered,'execute_dispatch',revision=1)
        self.assertEqual(received['calendar_revision'],signal['calendar_revision'])
        self.assertNotEqual(received['case_revisions'],signal['case_revisions'])
        signal,received=self.act(flow,received,'read_delivery_discussion')
        self.assertEqual(signal,received)

    def test_delayed_authoritative_status_remains_a_new_event(self):
        flow=self.flow({'access':{'report_upload':'enabled'},'completion_basis':'contents',
                        'status_refresh_seconds':10})
        delivered=flow.activity_signal('a')
        signal,delivered=self.act(flow,delivered,'submit_report',item='summary',
            source_revision=s.SOURCE_REVISION,csv=s.payload(flow.plan['a'],'summary'))
        self.assertEqual(signal,delivered)
        self.assertTrue(flow.advance_business_time(10))
        self.assertNotEqual(flow.activity_signal('a')['calendar_revision'],delivered['calendar_revision'])

    def test_other_scenarios_keep_their_existing_receipt_contract(self):
        extension=SimpleNamespace(observed_activity_keys=lambda op,result:set(),
                                   observed_calendar_revision=lambda op,result:None)
        before={'revision':'before','calendar_revision':'before'}
        after={'revision':'after','calendar_revision':'after'}
        self.assertEqual(run.acknowledge_tool_activity(extension,'write',{},after,before,before),before)

    def shared_flow(self, config=None):
        flow = self.flow({'status_scope': 'reporting_close', **(config or {})})
        flow.activate()
        return flow

    def stage_again(self, flow, actor):
        plan = deepcopy(flow.plans[actor])
        plan.pop('revision')
        return flow.call(actor, len(flow.world.events)+1, 'stage_dispatch', plan)

    def test_identical_plan_versions_do_not_resume_observers(self):
        for author in ('a', 'b'):
            with self.subTest(author=author):
                flow = self.shared_flow()
                signal = flow.activity_signal('a')
                business = flow.goal_business_state('a')
                state = {}
                check = {'complete': False, 'actor_complete': False,
                         'actor_business_state': flow.business_state('a')}
                run.record_observed_work_revision(state, flow, check, signal)
                before = flow.plans[author]['revision']
                result = self.stage_again(flow, author)
                self.assertEqual(result['plan']['revision'], before+1)
                now = flow.activity_signal('a')
                self.assertEqual(now, signal)
                self.assertEqual(flow.goal_business_state('a'), business)
                check['actor_business_state'] = flow.business_state('a')
                self.assertFalse(run.followup_needed(state, flow, check, now))
                self.assertEqual(run.work_notice(extension=flow, actor='a',
                    check=check, signal=now, delivered=signal, state=state,
                    unfinished_followup=True), (None, None))

    def test_new_execution_still_resumes_observers(self):
        flow = self.shared_flow()
        before = flow.activity_signal('a')
        flow.call('b', 1, 'execute_dispatch', {'revision': 1})
        after = flow.activity_signal('a')
        self.assertNotEqual(before, after)
        check = {'complete': False, 'actor_complete': False,
                 'actor_business_state': flow.business_state('a')}
        self.assertEqual(run.work_notice(extension=flow, actor='a', check=check,
            signal=after, delivered=before)[1], 'relevant_platform_change')

    def test_delayed_version_refresh_remains_exact_without_a_notice(self):
        flow = self.shared_flow({'status_refresh_seconds': 10})
        before = flow.activity_signal('a')
        self.stage_again(flow, 'b')
        self.assertTrue(flow.has_pending_business_update())
        self.assertTrue(flow.advance_business_time(10))
        result = flow.call('a', 2, 'delivery_desk', {})
        account = flow.plan['b']['account']
        self.assertEqual(result['edition_check']['checked_revisions'][account], 2)
        self.assertEqual(flow.activity_signal('a'), before)
        self.assertFalse(flow.has_pending_business_update())

    def test_identical_plan_invalidating_a_release_is_still_new(self):
        flow = self.shared_flow({'completion_basis': 'contents',
                          'access': {'report_upload': 'enabled'}})
        for item in s.ITEMS:
            flow.call('b', 1, 'submit_report', {'item': item,
                'source_revision': s.SOURCE_REVISION,
                'csv': s.payload(flow.plan['b'], item)})
        result = flow.call('b', 2, 'release_delivery',
                          {'revision': flow.plans['b']['revision']})
        self.assertEqual(result['status'], 201)
        before = flow.activity_signal('a')
        self.stage_again(flow, 'b')
        self.assertNotEqual(flow.activity_signal('a'), before)
        self.assertNotIn('b', flow.deliveries)


if __name__=='__main__':unittest.main()
