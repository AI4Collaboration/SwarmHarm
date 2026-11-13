"""Scheduled Data consumer is a real source-backed process, not a model result."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from phase2 import delivery_data_partitions, delivery_paths, delivery_retention, mechanism_inputs, mechanism_review, world_config
from phase2.engineering_consumer import fixed_event_replay, observed_outcome, verify_export
from scripts.inspect_unified_input import build_preview

class DataScheduledConsumerChecks(unittest.TestCase):
    def test_paths_and_old_input_unchanged(self):
        old,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-partitions-v1')
        current,inputs=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
        plan=current['assignments']; fixed=mechanism_review.corrected_plan(plan)
        self.assertEqual(world_config.subject_inputs(fixed),inputs)
        self.assertEqual(mechanism_inputs.validate_plan('work-lifecycle',old['assignments'])['input_variant'],'data-partitions-v1')
        result=mechanism_inputs.validate_paths('work-lifecycle',plan)
        self.assertEqual(result['input_variant'],'data-scheduled-consumer-v1')
        self.assertFalse(result['ordinary_path']['normal_by_deadline'])
        self.assertTrue(result['ordinary_path']['safe_late_delivery'])
        self.assertTrue(result['ordinary_path']['corrected_binding_rejects_pending_cleanup'])

    def test_peer_observation_change_blocks_actor_omission_claim(self):
        with patch('phase2.engineering_consumer.CONSUMER_DELAY',.04), patch('phase2.engineering_consumer.DELIVERY_DEADLINE',.03):
            manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
            plan=manifest['assignments']; actors=list(plan); probe=delivery_paths.Probe(plan);probe.flow.activate()
            probe.call(actors[0],delivery_retention.CLEAN_ONE,snapshot='OPS-01')
            probe.call(actors[1],delivery_retention.READ)
            time.sleep(.06);probe.flow.advance_business_time(.06)
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize()
                without=fixed_event_replay(plan,probe.flow.world.events,actors[1:],root/'without',evidence_root=natural)
                self.assertFalse(without['retained_results_match'])
                self.assertTrue(any(row['operation']==delivery_retention.READ and not row['result_match'] for row in without['retained_actions']))

    def test_source_processing_missing_retry_and_replay(self):
        with patch('phase2.engineering_consumer.CONSUMER_DELAY',.04), patch('phase2.engineering_consumer.DELIVERY_DEADLINE',.03):
            manifest,_=build_preview('data-analysis','availability',mechanism='work-lifecycle',input_variant='data-scheduled-consumer-v1')
            plan=manifest['assignments']; actors=list(plan); probe=delivery_paths.Probe(plan)
            probe.flow.activate()
            probe.ordinary(actors[0]); self.assertEqual(probe.release(actors[0])['status'],409)
            self.assertEqual(probe.call(actors[0],delivery_retention.CLEAN_ONE,snapshot='OPS-01')['removed'],['OPS-01'])
            self.assertEqual(probe.release(actors[0])['status'],201)
            time.sleep(.06); self.assertTrue(probe.flow.advance_business_time(.06))
            self.assertEqual(probe.flow.world.events[-1]['result']['missing_inputs'],['OPS-01'])
            self.assertEqual(probe.call(actors[0],delivery_retention.RESTORE,snapshot='OPS-01')['status'],409)
            self.assertEqual(probe.call(actors[0],'withdraw_delivery')['status'],200)
            self.assertTrue(probe.call(actors[0],delivery_retention.RESTORE,snapshot='OPS-01')['changed'])
            time.sleep(.06);self.assertTrue(probe.flow.advance_business_time(.12))
            with TemporaryDirectory() as tmp:
                root=Path(tmp);natural=root/'natural';natural.mkdir();operator=natural/'operator';operator.mkdir()
                probe.flow.world.operator=operator;probe.flow.finalize();store=operator/'retention-store'
                self.assertTrue(verify_export(plan,store,delay_seconds=.04))
                facts=observed_outcome(plan,store,probe.flow.world.events,delay_seconds=.04)
                self.assertEqual(facts['first_attempt_missing'],['OPS-01']);self.assertEqual(facts['pending_at_end'],[])
                actual=list(csv.DictReader((operator/'delivery-files/data-operations.csv').read_text().splitlines()))
                for report in probe.flow.retention.orders:
                    assignment,part=delivery_retention.knowledge_assignment(plan,report)
                    expected=list(csv.DictReader(delivery_data_partitions.expected_consumer(assignment,part).decode().splitlines()))
                    self.assertEqual([{k:v for k,v in row.items() if k!='report'} for row in actual if row['report']==report],expected)
                joint=fixed_event_replay(plan,probe.flow.world.events,actors,root/'joint',evidence_root=natural)
                self.assertTrue(joint['retained_results_match']);self.assertEqual(joint['pending_at_end'],[])
                output=store/'consumer/0002/data-operations.csv';output.write_text(output.read_text().replace('alpha','tampered',1))
                self.assertFalse(verify_export(plan,store,delay_seconds=.04))

if __name__=='__main__':unittest.main()
