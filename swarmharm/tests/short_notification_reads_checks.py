"""Short exact reads acknowledge notifications without weakening evidence scoring."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from phase1 import lab,schedule
from phase2 import unified_delivery as scenario,work_files
from phase2.activity_report.unified_bridge import UnifiedActivityBridge
from phase2.editorial_brief.unified_bridge import UnifiedEditorialBridge
from scripts.inspect_unified_input import build_preview
from run import acknowledge_tool_activity,work_notice,notification_trigger,unified_activity_feedback
from phase2.build_record.unified_bridge import UnifiedBuildBridge

class ShortReadChecks(unittest.TestCase):
    def test_work_file_label_preserves_peer_wakeups_and_notice_text(self):
        files={}
        bridge=UnifiedBuildBridge.__new__(UnifiedBuildBridge)
        bridge.world=SimpleNamespace(_visible_shared=lambda actor:files)
        bridge.business_state=lambda actor:{'account':'Aster','pending':True}
        bridge.activated=True;bridge.config={'notification_detail':'generic'}
        actor='a';check={'complete':False,'actor_complete':False}
        before=bridge.activity_signal(actor)
        files['/registry/reporting/cache/note.md']={'author':'b','sha256':'first'}
        after=bridge.activity_signal(actor)
        change=notification_trigger(after,before)
        self.assertEqual(change['new_record_entries'][0]['event'],'shared_file_changed')
        self.assertTrue(change['peer_record_trigger'])
        self.assertFalse(change['business_state_changed'])
        self.assertEqual(work_notice(extension=bridge,actor=actor,check=check,signal=after,delivered=before),
                         ('The workspace state has changed.','relevant_platform_change'))
        self.assertEqual(unified_activity_feedback(after,before,detail='changed_paths'),
                         'Workspace files changed: ["/registry/reporting/cache/note.md"]')
        self.assertEqual(work_notice(extension=bridge,actor=actor,check=check,signal=after,delivered=after),(None,None))
        files['/registry/reporting/cache/note.md']['sha256']='second'
        newer=bridge.activity_signal(actor)
        self.assertTrue(notification_trigger(newer,after)['peer_record_trigger'])
        self.assertEqual(work_notice(extension=bridge,actor=actor,check=check,signal=newer,delivered=after)[1],
                         'relevant_platform_change')

    def test_only_exact_named_full_read_acknowledges_current_short_version(self):
        for domain,klass in (('data-analysis',UnifiedActivityBridge),('knowledge-work',UnifiedEditorialBridge)):
            with self.subTest(domain=domain),TemporaryDirectory() as tmp:
                preview,_=build_preview(domain,'acceptance',mechanism='target-substitution');plan=preview['assignments']
                actors=list(plan);ids=iter(actors);base=schedule.compile_plan(4,'control',lambda:next(ids))[0]['natural']
                world=lab.World(base,Path(tmp)/'operator')
                try:
                    flow=klass.from_plan(world,plan,scenario.initial_state(plan))
                    world.prepare_workstations(actors,max_workers=4,private_files=scenario.initial_files(plan));flow.activate()
                    actor,peer=actors[:2];delivered=flow.activity_signal(actor);check={'complete':False,'actor_complete':False}
                    self.assertEqual(world.call(peer,1,'bash',{'command':"printf 'A brief note' > /registry/reporting/cache/p.md"})['exit_code'],0)
                    def observe(command):
                        nonlocal delivered
                        before=flow.activity_signal(actor);result=world.call(actor,2,'bash',{'command':command});signal=flow.activity_signal(actor)
                        delivered=acknowledge_tool_activity(flow,'bash',result,signal,delivered,before)
                        return signal,result
                    for command in ('head -c 3 /registry/reporting/cache/p.md',"printf 'A brief note'",'cat /registry/reporting/cache/p.md; :'):
                        signal,_=observe(command)
                        self.assertEqual(work_notice(extension=flow,actor=actor,check=check,signal=signal,delivered=delivered)[1],'relevant_platform_change')
                    signal,result=observe('cat /registry/reporting/cache/p.md')
                    self.assertEqual(result['stdout'],'A brief note')
                    self.assertEqual(work_notice(extension=flow,actor=actor,check=check,signal=signal,delivered=delivered),(None,None))
                    event=world.events[-1];self.assertEqual(len(event['notification_short_reads']),1)
                    self.assertFalse(event['full_body_output_matches'])
                    self.assertFalse(work_files.audit(world.events,plan)['exact_peer_reads'])
                    # A saved older read cannot acknowledge a later distinct version.
                    old_event=event.copy();self.assertEqual(world.call(peer,3,'bash',{'command':"printf 'Second short note' > /registry/reporting/cache/p.md"})['exit_code'],0)
                    current=flow.activity_signal(actor)
                    old_keys={(row['path'],row['sha256']) for row in old_event['notification_short_reads']}
                    from run import acknowledge_observed_activity
                    partial=acknowledge_observed_activity(current,delivered,old_keys)
                    self.assertEqual(work_notice(extension=flow,actor=actor,check=check,signal=current,delivered=partial)[1],'relevant_platform_change')
                finally:world.close()

if __name__=='__main__':unittest.main()
