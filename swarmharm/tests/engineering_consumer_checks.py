"""Focused isolated consumer checks; no model calls."""
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from phase2 import delivery_paths,delivery_retention,unified_delivery
from phase2.engineering_consumer import ConsumerStore,verify_export,observed_outcome
from scripts.inspect_unified_input import build_preview


class EngineeringConsumerChecks(unittest.TestCase):
    def setUp(self):
        manifest,_=build_preview('engineering-capacity','availability',mechanism='work-lifecycle')
        self.plan=manifest['assignments'];self.actor=next(iter(self.plan));self.probe=delivery_paths.Probe(self.plan)
        self.store=ConsumerStore(self.plan,unified_delivery.RESERVE_REPORTS,retention_checked=False,
                                 delay_seconds=.04,executions=lambda:self.probe.flow.executions)
        self.probe.flow.retention=self.store;self.store.activate()
        self.store.on_consumer_event=lambda result:self.probe.flow._append_event(
            {'actor':None,'step':0,'operation':'operations_consumer_completed','arguments':{},
             'continuation':False,'shared_changes':[],'authored_artifacts':[],'result':result},event_at=result['at'])

    def test_observation_budget_is_bounded_and_requires_first_attempt(self):
        from phase2.engineering_consumer import remaining_observation_limit
        self.assertEqual(remaining_observation_limit(500, 450), 445)
        with self.assertRaises(ValueError):
            remaining_observation_limit(500, 364)
        self.store.observation_limit = .06
        self.assertTrue(self.store.pending_in_window())
        self.store.due = self.store.origin + .07
        self.assertFalse(self.store.pending_in_window())

    def test_missing_and_recovery_have_actual_receipts(self):
        self.probe.call(self.actor,delivery_retention.CLEAN_ONE,snapshot='OPS-01')
        time.sleep(.06);first=self.store.consume_due()
        self.assertEqual(first['missing_inputs'],['OPS-01']);self.assertEqual(len(first['completed']),7)
        self.assertTrue(self.probe.call(self.actor,delivery_retention.RESTORE,snapshot='OPS-01')['changed'])
        time.sleep(.06);second=self.store.consume_due()
        self.assertEqual(second['completed'],['OPS-01'])
        with TemporaryDirectory() as tmp:
            target=Path(tmp)/'store';self.store.export(target)
            self.assertTrue(verify_export(self.plan,target,delay_seconds=.04))
            outcome=observed_outcome(self.plan,target,self.probe.flow.world.events,delay_seconds=.04)
            self.assertEqual(outcome['first_attempt_missing'],['OPS-01'])
            self.assertEqual(outcome['pending_at_end'],[])
            self.assertFalse(outcome['causal_counterfactual_verified'])
            (target/'consumer'/'0002'/'engineering-operations.csv').write_text('tampered')
            self.assertFalse(verify_export(self.plan,target,delay_seconds=.04))

    def test_restore_before_window_and_cleanup_after_consumption(self):
        self.store.action(self.actor,delivery_retention.CLEAN_ONE,{'snapshot':'OPS-01'})
        self.assertTrue(self.store.action(self.actor,delivery_retention.RESTORE,{'snapshot':'OPS-01'})['changed'])
        time.sleep(.06);event=self.store.consume_due()
        self.assertEqual(event['missing_inputs'],[]);self.assertEqual(len(event['completed']),8)
        self.assertEqual(self.store.snapshot()['artifacts'][0]['pending_operations_consumers'],[])

    def test_complete_actor_omission_replays_actual_consumer_time(self):
        from phase2.engineering_consumer import fixed_event_replay
        with patch('phase2.engineering_consumer.CONSUMER_DELAY',.04), \
             patch('phase2.engineering_consumer.DELIVERY_DEADLINE',.03):
            manifest,_=build_preview('engineering-capacity','availability',mechanism='work-lifecycle',
                                     input_variant='engineering-scheduled-consumer-v1')
            plan=manifest['assignments'];probe=delivery_paths.Probe(plan);actors=list(plan)
            probe.flow.activate()
            probe.call(actors[0],delivery_retention.CLEAN_ONE,snapshot='OPS-01')
            time.sleep(.06);self.assertTrue(probe.flow.advance_business_time(.06))
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize()
                events=probe.flow.world.events
                actual=fixed_event_replay(plan,events,actors,root/'joint',evidence_root=natural)
                self.assertEqual(actual['first_attempt_missing'],['OPS-01'])
                self.assertTrue(actual['retained_results_match'])
                from phase2.engineering_consumer import store_fingerprint
                self.assertEqual(actual['store_fingerprint'],store_fingerprint(operator/'retention-store'))
                (operator/'retention-store'/'archive'/'OPS-01.csv').write_text('altered')
                self.assertNotEqual(actual['store_fingerprint'],store_fingerprint(operator/'retention-store'))
                # Restore from the independently generated replay before the next control.
                (operator/'retention-store'/'archive'/'OPS-01.csv').write_bytes(
                    (root/'joint'/'retention-store'/'archive'/'OPS-01.csv').read_bytes())
                without=fixed_event_replay(plan,events,actors[1:],root/'without',evidence_root=natural)
                self.assertEqual(without['first_attempt_missing'],[])
                self.assertTrue(without['retained_results_match'])

    def test_replay_preserves_observed_retry_schedule(self):
        from phase2.engineering_consumer import fixed_event_replay
        with patch('phase2.engineering_consumer.CONSUMER_DELAY',.04), \
             patch('phase2.engineering_consumer.DELIVERY_DEADLINE',.03):
            manifest,_=build_preview('engineering-capacity','availability',mechanism='work-lifecycle',
                                     input_variant='engineering-scheduled-consumer-v1')
            plan=manifest['assignments'];probe=delivery_paths.Probe(plan);actors=list(plan)
            probe.flow.activate()
            probe.call(actors[0],delivery_retention.CLEAN_ONE,snapshot='OPS-01')
            time.sleep(.06);probe.flow.advance_business_time(.06)
            probe.call(actors[0],delivery_retention.RESTORE,snapshot='OPS-01')
            probe.call(actors[1],delivery_retention.READ)
            time.sleep(.06);probe.flow.advance_business_time(.12)
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize()
                actual=fixed_event_replay(plan,probe.flow.world.events,actors,root/'joint',evidence_root=natural)
                self.assertTrue(actual['retained_results_match'], actual['retained_actions'])
                self.assertEqual(actual['pending_at_end'],[])

    def test_replay_keeps_cross_actor_inventory_observations(self):
        from phase2.engineering_consumer import fixed_event_replay
        with patch('phase2.engineering_consumer.CONSUMER_DELAY',.04), \
             patch('phase2.engineering_consumer.DELIVERY_DEADLINE',.03):
            manifest,_=build_preview('engineering-capacity','availability',mechanism='work-lifecycle',
                                     input_variant='engineering-scheduled-consumer-v1')
            plan=manifest['assignments'];probe=delivery_paths.Probe(plan);actors=list(plan)
            probe.flow.activate()
            probe.call(actors[0],delivery_retention.CLEAN_ONE,snapshot='OPS-01')
            probe.call(actors[1],delivery_retention.READ)
            probe.call(actors[1],delivery_retention.CLEAN_ONE,snapshot='OPS-02')
            time.sleep(.06);probe.flow.advance_business_time(.06)
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize()
                without=fixed_event_replay(plan,probe.flow.world.events,actors[1:],root/'without',evidence_root=natural)
                self.assertEqual(without['first_attempt_missing'],['OPS-02'])
                self.assertFalse(without['retained_results_match'])
                self.assertTrue(any(row['operation']==delivery_retention.READ and not row['result_match']
                                    for row in without['retained_actions']))

    def test_any_business_call_processes_a_due_consumer_first(self):
        from datetime import datetime, timedelta, timezone
        manifest,_=build_preview('engineering-capacity','availability',mechanism='work-lifecycle',
                                 input_variant='engineering-scheduled-consumer-v1')
        probe=delivery_paths.Probe(manifest['assignments']);actor=next(iter(manifest['assignments']))
        class Clock:
            now=0.0
            start=datetime.now(timezone.utc)
            def monotonic(self):return self.now
            def wall(self):return self.start+timedelta(seconds=self.now)
        clock=Clock();probe.flow.retention.clock=clock.monotonic;probe.flow.retention.wall=clock.wall
        probe.flow.activate();clock.now=360
        probe.call(actor,'check_delivery')
        events=probe.flow.world.events
        self.assertEqual(events[-2]['operation'],'operations_consumer_completed')
        self.assertEqual(events[-1]['operation'],'check_delivery')
        self.assertEqual(len(events[-2]['result']['completed']),8)
        self.assertFalse(probe.flow.has_pending_business_update())

    def test_unified_timer_emits_actual_consumer_event(self):
        from datetime import datetime, timedelta, timezone
        manifest,_=build_preview('engineering-capacity','availability',mechanism='work-lifecycle',
                                 input_variant='engineering-scheduled-consumer-v1')
        probe=delivery_paths.Probe(manifest['assignments'])
        class Clock:
            now=0.0
            start=datetime.now(timezone.utc)
            def monotonic(self):return self.now
            def wall(self):return self.start+timedelta(seconds=self.now)
        clock=Clock();probe.flow.retention.clock=clock.monotonic;probe.flow.retention.wall=clock.wall
        probe.flow.activate()
        self.assertTrue(probe.flow.has_pending_business_update())
        self.assertFalse(probe.flow.advance_business_time(100))
        clock.now=360
        self.assertTrue(probe.flow.advance_business_time(360))
        event=probe.flow.world.events[-1]
        self.assertEqual(event['operation'],'operations_consumer_completed')
        self.assertEqual(event['at'],event['result']['at'])
        self.assertEqual(len(event['result']['completed']),8)
        self.assertFalse(probe.flow.has_pending_business_update())
        with TemporaryDirectory() as tmp:
            probe.flow.world.operator=Path(tmp)
            probe.flow.finalize()
            target=Path(tmp)/'retention-store'
            self.assertTrue(verify_export(manifest['assignments'],target,delay_seconds=360))

    def test_unified_actual_output_tracks_consumption_not_final_store(self):
        from datetime import datetime, timedelta, timezone
        manifest,_=build_preview('engineering-capacity','availability',mechanism='work-lifecycle',
                                 input_variant='engineering-scheduled-consumer-v1')
        probe=delivery_paths.Probe(manifest['assignments']);actor=next(iter(manifest['assignments']))
        class Clock:
            now=0.0
            start=datetime.now(timezone.utc)
            def monotonic(self):return self.now
            def wall(self):return self.start+timedelta(seconds=self.now)
        clock=Clock();probe.flow.retention.clock=clock.monotonic;probe.flow.retention.wall=clock.wall
        probe.flow.activate()
        probe.call(actor,delivery_retention.CLEAN_ONE,snapshot='OPS-01')
        clock.now=360;probe.flow.advance_business_time(360)
        probe.call(actor,delivery_retention.RESTORE,snapshot='OPS-01')
        clock.now=720;probe.flow.advance_business_time(720)
        with TemporaryDirectory() as tmp:
            probe.flow.world.operator=Path(tmp);probe.flow.finalize()
            root=Path(tmp);target=root/'retention-store'
            self.assertTrue(verify_export(manifest['assignments'],target,delay_seconds=360))
            import csv
            with (root/'delivery-files'/'operations-reports.csv').open() as stream:
                final=list(csv.DictReader(stream))
            self.assertEqual(len(final),8)
            first=__import__('json').loads((target/'consumer'/'0001'/'receipt.json').read_text())
            self.assertEqual(first['missing_inputs'],['OPS-01'])

    def test_native_binding_fails_closed(self):
        from phase2.engineering_consumer import bind_native
        event={'id':1,'actor':self.actor,'operation':'clean_reporting_snapshot','arguments':{'snapshot':'OPS-01'},'continuation':True}
        with patch('phase2.communication_evidence.bind_events',return_value={}):
            with self.assertRaisesRegex(ValueError,'Missing exact native'):
                bind_native('/unused',{'events':[event]},[self.actor])

    def test_deadline_paths_keep_safe_waiting_and_withdrawal(self):
        from datetime import datetime, timedelta, timezone
        class Clock:
            now=0.0
            start=datetime.now(timezone.utc)
            def monotonic(self):return self.now
            def wall(self):return self.start+timedelta(seconds=self.now)
        def setup(checked):
            probe=delivery_paths.Probe(self.plan);clock=Clock()
            store=ConsumerStore(self.plan,unified_delivery.RESERVE_REPORTS,retention_checked=checked,
                delay_seconds=360,deadline_seconds=300,executions=lambda:probe.flow.executions,
                clock=clock.monotonic,wall=clock.wall)
            probe.flow.retention=store;store.activate()
            return probe,store,clock
        normal,normal_store,normal_clock=setup(True)
        alternate,alternate_store,alternate_clock=setup(False)
        actors=list(self.plan)
        for probe in (normal,alternate):
            for actor in actors:
                probe.ordinary(actor)
                self.assertEqual(probe.release(actor)['status'],409)
        for actor,snapshot in zip(actors,unified_delivery.RESERVE_REPORTS[:4]):
            self.assertEqual(normal.call(actor,delivery_retention.CLEAN_ONE,snapshot=snapshot)['removed'],[])
            self.assertEqual(alternate.call(actor,delivery_retention.CLEAN_ONE,snapshot=snapshot)['removed'],[snapshot])
            self.assertEqual(alternate.release(actor)['status'],201)
        alternate.call(actors[0],'withdraw_delivery')
        self.assertTrue(alternate.call(actors[0],delivery_retention.RESTORE,snapshot='OPS-01')['changed'])
        normal_clock.now=alternate_clock.now=360
        self.assertEqual(len(normal_store.consume_due()['completed']),8)
        actual=alternate_store.consume_due()
        self.assertEqual(actual['missing_inputs'],list(unified_delivery.RESERVE_REPORTS[1:4]))
        self.assertGreater(normal_clock.now,300)
        for actor,snapshot in zip(actors,unified_delivery.RESERVE_REPORTS[:4]):
            self.assertEqual(normal.call(actor,delivery_retention.CLEAN_ONE,snapshot=snapshot)['removed'],[snapshot])
            self.assertEqual(normal.release(actor)['status'],201)

    def test_synthetic_calendar_is_truthful_and_ordered(self):
        from datetime import datetime
        timed=ConsumerStore(self.plan,unified_delivery.RESERVE_REPORTS,retention_checked=False,
                            delay_seconds=360,deadline_seconds=300,executions=lambda:[])
        timed.activate();view=timed.snapshot()
        self.assertLess(datetime.fromisoformat(view['delivery_due_at']),
                        datetime.fromisoformat(view['operations_scheduled_at']))
        with self.assertRaisesRegex(ValueError,'calendar'):
            ConsumerStore(self.plan,unified_delivery.RESERVE_REPORTS,retention_checked=False,
                          delay_seconds=300,deadline_seconds=360,executions=lambda:[])

    def test_due_event_precedes_cleanup(self):
        time.sleep(.06)
        result=self.store.action(self.actor,delivery_retention.CLEAN_ONE,{'snapshot':'OPS-01'})
        self.assertEqual(result['removed'],['OPS-01'])
        self.assertIn('OPS-01',self.store.completed)
        self.assertTrue((self.store.consumer/'0001'/'receipt.json').exists())

if __name__=='__main__':unittest.main()
