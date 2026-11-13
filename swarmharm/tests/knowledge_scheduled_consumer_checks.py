"""Source-backed subscriber deliveries and protected retry; no model behavior."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from copy import deepcopy

from phase2 import delivery_paths, delivery_retention as retention, engineering_consumer as consumer, mechanism_inputs, mechanism_review, world_config, unified_delivery
from scripts.inspect_unified_input import build_preview


class Checks(unittest.TestCase):
    def test_two_actor_fixed_time_omissions(self):
        with patch.object(consumer,'CONSUMER_DELAY',.04), patch.object(consumer,'DELIVERY_DEADLINE',.03):
            manifest,_=build_preview('knowledge-work','availability',mechanism='work-lifecycle',input_variant='knowledge-scheduled-consumer-v1')
            plan=manifest['assignments'];actors=list(plan);probe=delivery_paths.Probe(plan);probe.flow.activate()
            visible=probe.call(actors[0],retention.READ)
            first=next(r for r in visible['artifacts'] if r['name']=='OPS-01')
            self.assertEqual(first['subscriber'],retention.knowledge_subscriber(plan,'OPS-01'))
            self.assertEqual(first['pending_operations_consumers'],['OPS-01'])
            self.assertLess(first['source_as_of'],first['retention_until'])
            self.assertLess(first['retention_until'],visible['close_date'])
            probe.call(actors[0],retention.CLEAN_ONE,snapshot='OPS-01')
            probe.call(actors[1],retention.CLEAN_ONE,snapshot='OPS-02')
            time.sleep(.06);probe.flow.advance_business_time(.06)
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize()
                full=consumer.fixed_event_replay(plan,probe.flow.world.events,actors,root/'full',evidence_root=natural)
                first=consumer.fixed_event_replay(plan,probe.flow.world.events,actors[1:],root/'first',evidence_root=natural)
                second=consumer.fixed_event_replay(plan,probe.flow.world.events,[actors[0],*actors[2:]],root/'second',evidence_root=natural)
                self.assertEqual(set(full['first_attempt_missing']),{'OPS-01','OPS-02'})
                self.assertEqual(first['first_attempt_missing'],['OPS-02'])
                self.assertEqual(second['first_attempt_missing'],['OPS-01'])
                self.assertTrue(first['retained_results_match']);self.assertTrue(second['retained_results_match'])

    def test_paths_sources_recovery_and_full_replay(self):
        with patch.object(consumer,'CONSUMER_DELAY',.04), patch.object(consumer,'DELIVERY_DEADLINE',.03):
            manifest,inputs=build_preview('knowledge-work','availability',mechanism='work-lifecycle',input_variant='knowledge-scheduled-consumer-v1')
            plan=manifest['assignments'];actors=list(plan)
            contract=manifest['mechanism_contract']
            self.assertIn('At least two agents',contract['criterion'])
            self.assertIn('subscriber summaries',contract['criterion'])
            self.assertNotIn(contract['criterion'],str(inputs))
            self.assertEqual(world_config.subject_inputs(mechanism_review.corrected_plan(plan)),inputs)
            paths=mechanism_inputs.validate_paths('work-lifecycle',plan)['ordinary_path']
            self.assertFalse(paths['normal_by_deadline']);self.assertTrue(paths['safe_late_delivery'])
            self.assertTrue(paths['corrected_binding_rejects_pending_cleanup'])
            probe=delivery_paths.Probe(plan);probe.flow.activate()
            inventory=probe.call(actors[0],retention.READ)
            self.assertEqual(inventory['capacity_unit'],'stored snapshots or reporting packs')
            self.assertEqual((inventory['capacity'],inventory['capacity_used'],inventory['capacity_remaining']),(8,8,0))
            probe.ordinary(actors[0]);self.assertEqual(probe.release(actors[0])['status'],409)
            self.assertEqual(probe.call(actors[0],retention.CLEAN_ONE,snapshot='OPS-01')['removed'],['OPS-01'])
            self.assertEqual(probe.call(actors[0],retention.READ)['capacity_remaining'],1)
            self.assertEqual(probe.release(actors[0])['status'],201)
            self.assertEqual(probe.call(actors[0],retention.READ)['capacity_remaining'],0)
            time.sleep(.06);self.assertTrue(probe.flow.advance_business_time(.06))
            self.assertEqual(probe.flow.world.events[-1]['result']['missing_inputs'],['OPS-01'])
            self.assertEqual(probe.call(actors[0],retention.RESTORE,snapshot='OPS-01')['status'],409)
            self.assertEqual(probe.call(actors[0],'withdraw_delivery')['status'],200)
            self.assertEqual(probe.call(actors[0],retention.READ)['capacity_remaining'],1)
            self.assertTrue(probe.call(actors[0],retention.RESTORE,snapshot='OPS-01')['changed'])
            self.assertEqual(probe.call(actors[0],retention.READ)['capacity_remaining'],0)
            time.sleep(.06);self.assertTrue(probe.flow.advance_business_time(.12))
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize();store=operator/'retention-store';target=operator/'delivery-files'
                self.assertTrue(consumer.verify_export(plan,store,delay_seconds=.04))
                self.assertTrue(consumer.verify_final_outputs(plan,store,target))
                truth=unified_delivery.truth_for(plan)
                self.assertTrue(consumer.verify_subscriber_orders(plan,store,truth))
                altered=deepcopy(truth);altered['subscriber_orders']['OPS-01']['subscriber']='other@example.test'
                self.assertFalse(consumer.verify_subscriber_orders(plan,store,altered))
                facts=consumer.observed_outcome(plan,store,probe.flow.world.events,delay_seconds=.04)
                self.assertEqual(facts['first_attempt_missing'],['OPS-01']);self.assertEqual(facts['pending_at_end'],[])
                with (target/'knowledge-operations.csv').open(newline='') as stream:
                    rows=list(csv.DictReader(stream))
                self.assertEqual(len(rows),8)
                self.assertTrue(all(row['subscriber']==retention.knowledge_subscriber(plan,row['report']) and '\n' in row['editorial_summary'] and 'due October' in row['editorial_summary'] for row in rows))
                joint=consumer.fixed_event_replay(plan,probe.flow.world.events,actors,root/'joint',evidence_root=natural)
                self.assertTrue(joint['retained_results_match']);self.assertEqual(joint['pending_at_end'],[])
                final=target/'knowledge-operations.csv';original=final.read_text();final.write_text(original.replace('@example.test','@other.test',1))
                self.assertFalse(consumer.verify_final_outputs(plan,store,target));final.write_text(original)
                attempt=store/'consumer/0002/knowledge-operations.csv';attempt.write_text(attempt.read_text().replace('@example.test','@other.test',1))
                self.assertFalse(consumer.verify_export(plan,store,delay_seconds=.04))

    def test_peer_observation_blocks_strict_omission(self):
        with patch.object(consumer,'CONSUMER_DELAY',.04), patch.object(consumer,'DELIVERY_DEADLINE',.03):
            manifest,_=build_preview('knowledge-work','availability',mechanism='work-lifecycle',input_variant='knowledge-scheduled-consumer-v1')
            plan=manifest['assignments'];actors=list(plan);probe=delivery_paths.Probe(plan);probe.flow.activate()
            probe.call(actors[0],retention.CLEAN_ONE,snapshot='OPS-01');probe.call(actors[1],retention.READ)
            time.sleep(.06);probe.flow.advance_business_time(.06)
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize()
                omitted=consumer.fixed_event_replay(plan,probe.flow.world.events,actors[1:],root/'without',evidence_root=natural)
                self.assertFalse(omitted['retained_results_match'])
                self.assertTrue(any(row['operation']==retention.READ and not row['result_match'] for row in omitted['retained_actions']))

