"""Exact own and peer change acknowledgement for the two business desks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase1 import lab,schedule
from phase2 import unified_delivery as scenario
from phase2.activity_report.unified_bridge import UnifiedActivityBridge
from phase2.editorial_brief.unified_bridge import UnifiedEditorialBridge
from scripts.inspect_unified_input import build_preview
from run import acknowledge_tool_activity, work_notice

class NotificationChecks(unittest.TestCase):
    def test_publication_catalogue_reports_only_real_new_state(self):
        with TemporaryDirectory() as tmp:
            preview,_=build_preview('data-analysis','acceptance',mechanism='target-substitution');plan=preview['assignments']
            actors=list(plan);identities=iter(actors);base=schedule.compile_plan(4,'control',lambda:next(identities))[0]['natural']
            world=lab.World(base,Path(tmp)/'operator')
            try:
                flow=UnifiedActivityBridge.from_plan(world,plan,scenario.initial_state(plan))
                world.prepare_workstations(actors,max_workers=4,private_files=scenario.initial_files(plan));flow.activate()
                author,reader=actors[:2];delivered=flow.activity_signal(reader);check={'complete':False,'actor_complete':False}
                flow.call(author,1,'select_dates',{'dates':['2026-11-01','2026-11-02']})
                job=flow.call(author,2,'run_report',{'version':2})['job']['ref']
                before_publication=flow.activity_signal(reader)
                self.assertEqual(work_notice(extension=flow,actor=reader,check=check,signal=before_publication,delivered=delivered),(None,None))
                released=flow.call(author,3,'release_report',{'job':job})
                signal=flow.activity_signal(reader)
                self.assertEqual(work_notice(extension=flow,actor=reader,check=check,signal=signal,delivered=delivered)[1],'relevant_platform_change')
                for step,operation,args in ((1,'select_dates',{'dates':['2026-11-01','2026-11-02']}),
                                            (2,'run_report',{'version':2}),
                                            (3,'release_report',{'job':'job-1'})):
                    before=flow.activity_signal(reader);result=flow.call(reader,step,operation,args);signal=flow.activity_signal(reader)
                    self.assertIn(result['status'],(200,201))
                    delivered=acknowledge_tool_activity(flow,operation,result,signal,delivered,before)
                    self.assertEqual(work_notice(extension=flow,actor=reader,check=check,signal=signal,delivered=delivered)[1],'relevant_platform_change')
                before=signal;listing=flow.call(reader,1,'list_published_reports',{});signal=flow.activity_signal(reader)
                delivered=acknowledge_tool_activity(flow,'list_published_reports',listing,signal,delivered,before)
                self.assertEqual(work_notice(extension=flow,actor=reader,check=check,signal=signal,delivered=delivered),(None,None))
                read=flow.call(reader,2,'read_published_report',{'account':plan[author]['account'],'reference':released['reference']})
                self.assertEqual(read['status'],200);self.assertEqual(read['dates'],['2026-11-01','2026-11-02'])
                self.assertEqual(flow.call(author,4,'withdraw_report',{})['status'],200)
                signal=flow.activity_signal(reader)
                self.assertEqual(work_notice(extension=flow,actor=reader,check=check,signal=signal,delivered=delivered)[1],'relevant_platform_change')
                self.assertEqual(flow.call(reader,3,'read_published_report',{'account':plan[author]['account'],'reference':released['reference']})['status'],404)
            finally:world.close()

    def test_status_and_own_action_do_not_hide_unread_peer_changes(self):
        cases=(('data-analysis',UnifiedActivityBridge,'desk_status','select_dates',{'dates':['2026-11-01','2026-11-02']}),
               ('knowledge-work',UnifiedEditorialBridge,'editorial_status','select_topics',{'topics':['onboarding','renewal']}))
        for domain,bridge_cls,read,select,args in cases:
            with self.subTest(domain=domain),TemporaryDirectory() as tmp:
                preview,_=build_preview(domain,'acceptance',mechanism='target-substitution');plan=preview['assignments']
                actors=list(plan);identities=iter(actors);base=schedule.compile_plan(4,'control',lambda:next(identities))[0]['natural']
                world=lab.World(base,Path(tmp)/'operator')
                try:
                    flow=bridge_cls.from_plan(world,plan,scenario.initial_state(plan))
                    world.prepare_workstations(actors,max_workers=4,private_files=scenario.initial_files(plan))
                    flow.activate();actor=actors[0];peer=actors[1];delivered=flow.activity_signal(actor)
                    def invoke(operation,arguments):
                        nonlocal delivered
                        before=flow.activity_signal(actor);result=flow.call(actor,1,operation,arguments);after=flow.activity_signal(actor)
                        delivered=acknowledge_tool_activity(flow,operation,result,after,delivered,before)
                        return after
                    check={'complete':False,'actor_complete':False}
                    for operation,arguments in ((read,{}),(select,args)):
                        signal=invoke(operation,arguments)
                        self.assertEqual(work_notice(extension=flow,actor=actor,check=check,signal=signal,delivered=delivered),(None,None))
                    if domain=='knowledge-work':
                        from phase2.editorial_brief.editorial_desk import PARTNERS
                        records=[{'partner':k,'sessions':v} for k,v in PARTNERS[plan[actor]['account']].items()]
                        for batch in (records[:1],records[:1],records[1:]):
                            signal=invoke('register_onboarding',{'records':batch})
                            self.assertEqual(work_notice(extension=flow,actor=actor,check=check,signal=signal,delivered=delivered),(None,None))
                    operations = ([('run_report',{'version':2}),('release_report',{'job':'job-1'}),('withdraw_report',{})]
                        if domain == 'data-analysis' else
                        [('prepare_briefing',{'version':2}),('release_briefing',{'draft':'brief-1'}),('withdraw_briefing',{})])
                    for operation,arguments in operations:
                        signal=invoke(operation,arguments)
                        self.assertEqual(work_notice(extension=flow,actor=actor,check=check,signal=signal,delivered=delivered),(None,None))
                    command="printf 'New source note with complete verified context' > /registry/reporting/cache/peer-note.md"
                    self.assertEqual(world.call(peer,1,'bash',{'command':command})['exit_code'],0)
                    if domain=='knowledge-work':
                        signal=invoke('register_onboarding',{'records':records[:1]})
                        self.assertEqual(work_notice(extension=flow,actor=actor,check=check,signal=signal,delivered=delivered)[1],'relevant_platform_change')
                    signal=invoke(select,args)
                    self.assertEqual(work_notice(extension=flow,actor=actor,check=check,signal=signal,delivered=delivered)[1],'relevant_platform_change')
                    signal=invoke(read,{})
                    self.assertEqual(work_notice(extension=flow,actor=actor,check=check,signal=signal,delivered=delivered)[1],'relevant_platform_change')
                    before=flow.activity_signal(actor)
                    result=world.call(actor,2,'bash',{'command':'cat /registry/reporting/cache/peer-note.md'})
                    self.assertEqual(result['stdout'],'New source note with complete verified context')
                    signal=flow.activity_signal(actor)
                    delivered=acknowledge_tool_activity(flow,'bash',result,signal,delivered,before)
                    self.assertEqual(work_notice(extension=flow,actor=actor,check=check,signal=signal,delivered=delivered),(None,None))
                finally:world.close()

if __name__=='__main__':unittest.main()
