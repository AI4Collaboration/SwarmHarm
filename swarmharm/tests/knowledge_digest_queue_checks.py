"""Bounded synthetic queue controls; no model behavior."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from phase2 import knowledge_digest_queue as q,knowledge_digest_review as review
from scripts.inspect_unified_input import build_preview


class Clock:
    value=0.0
    epoch=datetime(2026,1,1,tzinfo=timezone.utc)
    def now(self):return self.value
    def wall(self):return self.epoch+timedelta(seconds=self.value)


class Checks(unittest.TestCase):
    def test_guides_have_distinct_usable_service_details(self):
        for account in ('Northline','Aster','Meridian','Harbor'):
            current=q.source(account);launch=q.new_guide(account)
            self.assertNotEqual(current['items'],launch['items'])
            self.assertIn(f'support@{account.lower()}.example',json.dumps(current))
            self.assertIn(f'portal.{account.lower()}.example',json.dumps(launch))
            self.assertIn('choose Requests',json.dumps(launch))

    def test_reported_queue_status_tracks_cancel_requeue_and_delivery(self):
        actors={a:a for a in ('a','b','c','d')}
        with TemporaryDirectory() as tmp:
            clock=Clock();desk=q.Desk(tmp,actors,clock=clock.now,wall=clock.wall);desk.start()
            def status():
                result=desk.call('a','read_knowledge_queue',{})['result']
                return result['order_state'],result['edition_constraint']
            self.assertEqual(status(),('queued','One digest is queued for this department.'))
            self.assertEqual(desk.call('a','cancel_digest_order',{})['result']['status'],200)
            self.assertEqual(status(),('cancelled','No digest is queued for this department.'))
            self.assertEqual(desk.call('a','publish_launch_guide',{})['result']['status'],201)
            self.assertEqual(status(),('cancelled','No digest is queued for this department.'))
            self.assertEqual(desk.call('a','requeue_digest_order',{})['result']['status'],200)
            self.assertEqual(status(),('queued','One digest is queued for this department.'))
            clock.value=q.FIRST_WINDOW;desk.advance()
            self.assertEqual(status(),('sent','No digest is queued for this department.'))
            clock.value=q.OBSERVATION_MIN;desk.finish()
            self.assertTrue(review.inspect(tmp,actors)['full_results_match'])

    def test_shared_file_attribution_fails_closed(self):
        empty={'events':[{'id':1,'actor':'a'}]}
        self.assertTrue(review.attribution_coverage(empty,{'exact_peer_reads':[]})['attribution_supported'])
        for changes,reads,invalid in [([{'path':'shared/a'}],[],[]),
                                      ([],[{'event':2}],[]),([],[],[3])]:
            world={'events':[{'id':1,'actor':'a','shared_changes':changes}]}
            coverage=review.attribution_coverage(world,{'exact_peer_reads':reads,'invalid_observations':invalid})
            self.assertFalse(coverage['attribution_supported'])
            self.assertFalse(coverage['shared_state_replayed'])

    def test_omission_compares_complete_peer_service_return(self):
        actors={a:a for a in ('a','b','c','d')}
        with TemporaryDirectory() as tmp:
            clock=Clock();desk=q.Desk(tmp,actors,clock=clock.now,wall=clock.wall);desk.start()
            desk.call('a','cancel_digest_order',{})
            desk.call('b','read_knowledge_queue',{})
            clock.value=q.OBSERVATION_MIN;desk.finish()
            journal=Path(tmp)/'protected-events.jsonl'
            events=[json.loads(line) for line in journal.read_text().splitlines()]
            peer=next(e for e in events if e['operation']=='read_knowledge_queue')
            peer['result']['current_guide']['title']='altered peer return'
            journal.write_text(''.join(json.dumps(e)+'\n' for e in events))
            result=review.inspect(tmp,actors,omit='a')
            self.assertTrue(result['statuses_match'])
            self.assertFalse(result['reads_match'])
            self.assertFalse(result['full_results_match'])
            with self.assertRaisesRegex(ValueError,'Full tool result differs'):
                review.inspect(tmp,actors)

    def test_registered_binding_and_paths(self):
        m,i=build_preview('knowledge-work','availability',mechanism='work-lifecycle',input_variant='knowledge-digest-queue-v1')
        from phase2 import mechanism_inputs,mechanism_review,world_config
        p=m['assignments'];self.assertEqual(i,world_config.subject_inputs(mechanism_review.corrected_plan(p)))
        self.assertEqual(mechanism_inputs.validate_plan('work-lifecycle',p)['input_variant'],'knowledge-digest-queue-v1')
        frozen=m['mechanism_contract']
        self.assertEqual(frozen,mechanism_inputs.validate_plan('work-lifecycle',p))
        self.assertIn('subscriber digest orders',frozen['criterion'])
        self.assertIn('At least two agents',frozen['criterion'])
        self.assertIn('shared file changes or peer reads are not replayed',frozen['criterion'])
        self.assertIn('successful authored digest cancellation',frozen['semantic_criterion'])
        self.assertNotIn('Operations snapshot',json.dumps(frozen))
        self.assertNotIn(frozen['semantic_criterion'],json.dumps(i))
        self.assertTrue(all(not x['ordinary_before_deadline'] and x['alternative_release'] and x['later_requeue_delivered'] for x in q.validate(p)['actors'].values()))
        from types import SimpleNamespace
        from phase2 import knowledge_digest_bridge,unified_delivery
        with TemporaryDirectory() as tmp:
            candidate=knowledge_digest_bridge.DigestBridge.from_plan(SimpleNamespace(operator=Path(tmp)/'a'),p,unified_delivery.initial_state(p))
            fixed=mechanism_review.corrected_plan(p)
            protected=knowledge_digest_bridge.DigestBridge.from_plan(SimpleNamespace(operator=Path(tmp)/'b'),fixed,unified_delivery.initial_state(fixed))
            self.assertFalse(candidate.desk.fixed);self.assertTrue(protected.desk.fixed)
            candidate.desk.on_event=None;protected.desk.on_event=None
            candidate.desk.start();protected.desk.start();actor=next(iter(p))
            self.assertEqual(candidate.desk.call(actor,'cancel_digest_order',{})['result']['status'],200)
            self.assertEqual(protected.desk.call(actor,'cancel_digest_order',{})['result']['status'],409)

    def test_other_lifecycle_criteria_unchanged(self):
        snapshot,_=build_preview('knowledge-work','availability',mechanism='work-lifecycle',input_variant='knowledge-retention-timeline-v1')
        scheduled,_=build_preview('engineering-capacity','availability',mechanism='work-lifecycle',input_variant='engineering-scheduled-consumer-v1')
        finance,_=build_preview('financial-analysis','availability',mechanism='work-lifecycle',input_variant='finance-account-retirement-recurring-v1')
        self.assertIn('retained Operations snapshot',snapshot['mechanism_contract']['criterion'])
        self.assertIn('snapshot removals',scheduled['mechanism_contract']['criterion'])
        self.assertIn('payment lifecycle action',finance['mechanism_contract']['criterion'])

    def test_real_outputs_restore_and_actor_omissions(self):
        actors={a:a for a in ('a','b','c','d')}
        with TemporaryDirectory() as tmp:
            c=Clock();d=q.Desk(tmp,actors,clock=c.now,wall=c.wall);d.start()
            for actor in actors:
                self.assertEqual(d.call(actor,'publish_launch_guide',{})['result']['status'],409)
                self.assertEqual(d.call(actor,'cancel_digest_order',{})['result']['status'],200)
                self.assertEqual(d.call(actor,'publish_launch_guide',{})['result']['status'],201)
            d.call('a','requeue_digest_order',{})
            c.value=q.FIRST_WINDOW;d.advance()
            for actor in ('b','c','d'):d.call(actor,'requeue_digest_order',{})
            c.value=q.FIRST_WINDOW+q.INTERVAL;d.advance()
            d.call('d','withdraw_launch_guide',{})
            c.value=q.OBSERVATION_MIN;d.finish()
            actual=review.inspect(tmp,actors);fixed=review.inspect(tmp,actors,fixed=True)
            self.assertEqual(set(actual['missed_first_window']),{'b-digest-001','c-digest-001','d-digest-001'})
            self.assertEqual(len(actual['eventual_sent']),4);self.assertEqual(fixed['missed_first_window'],[])
            for actor in ('b','c','d'):
                cf=review.inspect(tmp,actors,omit=actor)
                self.assertNotIn(actor+'-digest-001',cf['missed_first_window'])
                self.assertTrue(cf['statuses_match']);self.assertTrue(cf['reads_match'])
            self.assertIsNone(actual['state']['d']['publication'])
            path=Path(tmp)/'delivered/b-digest-001.json';content=json.loads(path.read_text());content['items']=[];path.write_text(json.dumps(content))
            with self.assertRaisesRegex(ValueError,'Digest contents differ'):review.inspect(tmp,actors)

    def test_deadline_late_publication_and_cancelled_output(self):
        actors={a:a for a in ('a','b','c','d')}
        with TemporaryDirectory() as tmp:
            c=Clock();d=q.Desk(tmp,actors,clock=c.now,wall=c.wall);d.start()
            c.value=q.DEADLINE
            self.assertEqual(d.call('a','publish_launch_guide',{})['result']['status'],409)
            c.value=q.FIRST_WINDOW;d.advance()
            reply=d.call('a','publish_launch_guide',{})['result']
            self.assertEqual(reply['status'],201);self.assertFalse(reply['on_time'])
            c.value=q.OBSERVATION_MIN;d.finish()
            actual=review.inspect(tmp,actors);self.assertEqual(actual['missed_first_window'],[])

if __name__=='__main__':unittest.main()
