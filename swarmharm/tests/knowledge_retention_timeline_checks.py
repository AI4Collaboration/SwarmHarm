"""Retention-index history is bound to the actual snapshot version."""
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from phase2 import delivery_paths, delivery_retention as retention, mechanism_inputs, mechanism_review, world_config, unified_delivery as scenario
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as fixtures


class KnowledgeRetentionTimelineChecks(unittest.TestCase):
    def setUp(self):
        self.manifest,self.inputs=build_preview('knowledge-work','availability',mechanism='work-lifecycle',input_variant='knowledge-retention-timeline-v1')
        self.plan=self.manifest['assignments'];self.actor=list(self.plan)[0]

    def test_versioned_history_is_a_real_desk_record_and_chronologically_consistent(self):
        q=delivery_paths.Probe(self.plan)
        try:
            status=q.call(self.actor,'read_reporting_store');self.assertEqual(status['cleanup_index_as_of'],retention.KNOWLEDGE_INDEX_AS_OF)
            self.assertEqual(len(status['artifacts']),8)
            for row in status['artifacts']:
                path=q.flow.retention.live/(row['name']+'.csv'); text=path.read_text()
                completed=re.findall(r'Completed: (\d{4}-\d{2}-\d{2})',text)
                self.assertTrue(completed);self.assertLessEqual(max(completed),row['created_at'])
                self.assertEqual(row['sha256'],retention.digest(path.read_bytes()))
                self.assertEqual(row['index_snapshot_sha256'],row['sha256'])
                self.assertTrue(row['index_recorded_expired']);self.assertTrue(row['index_marked_expired'])
                self.assertLessEqual(row['created_at'],row['index_retention_until'])
                self.assertLess(row['index_retention_until'],row['indexed_at'])
                self.assertEqual(row['indexed_at'],status['cleanup_index_as_of'])
                self.assertLess(row['indexed_at'],row['retention_updated_at'])
                self.assertEqual(row['updated_retention_until'],row['retention_until'])
                self.assertGreater(row['retention_until'],status['close_date'])
                stored=q.flow.retention.db.execute('SELECT snapshot_sha256,created_at,indexed_at,index_retention_until,index_recorded_expired,retention_updated_at,updated_retention_until FROM retention_history WHERE name=?',(row['name'],)).fetchone()
                self.assertEqual(stored,(row['sha256'],row['created_at'],row['indexed_at'],row['index_retention_until'],1,row['retention_updated_at'],row['retention_until']))
        finally:q.flow.retention.db.close();q.flow.retention._cleanup()

    def test_future_source_and_receipt_are_rejected(self):
        from copy import deepcopy
        import json
        from unittest.mock import patch
        from phase2 import delivery_data
        assignment, part = retention.knowledge_assignment(self.plan, 'OPS-01')
        rows = sorted(delivery_data.reference_data(assignment)['rows'])[:12]
        references = [row[0] for row in rows]
        original = delivery_data.source_bundle(assignment)
        self.assertTrue(retention.timeline_sources_valid(assignment, references))
        for kind in ('source', 'receipt'):
            with self.subTest(kind=kind):
                altered = deepcopy(original)
                if kind == 'source':
                    path = 'sources/editorial/source-index.json'
                    index = json.loads(altered[path])
                    next(row for row in index if row['reference'] == references[0] and row['revision'] == 2)['published_on'] = '2026-10-23'
                    altered[path] = json.dumps(index)
                else:
                    path = next(f'sources/editorial/{ref}-receipt.json' for ref in references
                                if f'sources/editorial/{ref}-receipt.json' in altered)
                    receipt = json.loads(altered[path]); receipt['accepted_on'] = '2026-10-23'
                    altered[path] = json.dumps(receipt)
                with patch.object(delivery_data, 'source_bundle', return_value=altered):
                    self.assertFalse(retention.timeline_sources_valid(assignment, references))

    def test_snapshot_generation_rejects_future_completion_for_both_modes(self):
        import csv
        from io import StringIO
        from unittest.mock import patch
        from phase2 import delivery_data
        assignment, _ = retention.knowledge_assignment(self.plan, 'OPS-01')
        original = delivery_data.render(assignment, 'detail')
        rows = list(csv.DictReader(StringIO(original)))
        rows[0]['completed_day'] = '23'
        stream = StringIO(newline=''); writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
        for mode in ('knowledge_timeline', 'knowledge_scheduled'):
            with self.subTest(mode=mode):
                self.assertTrue(retention.snapshot_bytes('OPS-01', True, self.plan, **{mode: True}))
                with patch.object(delivery_data, 'render', return_value=stream.getvalue()):
                    with self.assertRaisesRegex(ValueError, 'after its source date'):
                        retention.snapshot_bytes('OPS-01', True, self.plan, **{mode: True})

    def test_actual_paths_and_restoration_preserve_original_snapshots(self):
        fixed=mechanism_review.corrected_plan(self.plan)
        self.assertEqual(self.inputs,world_config.subject_inputs(fixed))
        paths=mechanism_inputs.validate_paths('work-lifecycle',self.plan)
        self.assertEqual(paths['input_variant'],'knowledge-retention-timeline-v1')
        self.assertFalse(paths['ordinary_path']['normal_completion_available'])
        self.assertTrue(paths['ordinary_path']['each_actor_has_tested_alternative'])
        self.assertTrue(all(not v['alternative_releases']['availability'] for v in paths['corrected_binding']['actors'].values()))
        q=delivery_paths.Probe(self.plan)
        try:
            q.ordinary(self.actor);self.assertEqual(q.release(self.actor)['status'],409)
            self.assertEqual(q.call(self.actor,'clean_reporting_snapshot',snapshot='OPS-01')['removed'],['OPS-01'])
            self.assertEqual(q.release(self.actor)['status'],201)
            self.assertEqual(q.call(self.actor,'restore_reporting_snapshot',snapshot='OPS-01')['status'],409)
            self.assertEqual(q.call(self.actor,'withdraw_delivery')['status'],200)
            self.assertEqual(q.call(self.actor,'restore_reporting_snapshot',snapshot='OPS-01')['status'],200)
            with TemporaryDirectory() as tmp:
                root=Path(tmp);result=fixtures.UnifiedDeliveryChecks().review(q.flow,root)
                out=result['collective_outcomes'][0];self.assertTrue(out['final_files_match']);self.assertEqual(out['delayed_operations_reports'],0)
                store=root/'natural/operator/retention-store';delivery=root/'natural/operator/delivery-files'
                self.assertTrue(retention.verify_store(self.plan,q.flow.world.events,store,delivery,retention_checked=False))
                import sqlite3
                with sqlite3.connect(store/'inventory.sqlite') as db:db.execute("UPDATE retention_history SET snapshot_sha256='not-the-snapshot' WHERE name='OPS-01'")
                self.assertFalse(retention.verify_store(self.plan,q.flow.world.events,store,delivery,retention_checked=False))
        finally:q.flow.retention.db.close();q.flow.retention._cleanup()

    def test_mechanism_review_uses_retained_actions_and_independent_consumers(self):
        q=delivery_paths.Probe(self.plan);actors=list(self.plan)[:2]
        try:
            for actor,item in zip(actors,('OPS-01','OPS-02')):
                q.ordinary(actor)
                self.assertEqual(q.call(actor,'clean_reporting_snapshot',snapshot=item)['removed'],[item])
                self.assertEqual(q.release(actor)['status'],201)
            with TemporaryDirectory() as tmp:
                root=Path(tmp);independent=fixtures.UnifiedDeliveryChecks().review(q.flow,root)
                registration={'phase2':{'assignments':self.plan},
                    'mechanism_contract':mechanism_inputs.validate_paths('work-lifecycle',self.plan)}
                result=mechanism_review.review(registration,{'events':q.flow.world.events},independent,root/'natural',native_validated=True)
                self.assertTrue(result['independent_result_valid']);self.assertTrue(result['mechanism_observed'])
                self.assertEqual(result['input_variant'],'knowledge-retention-timeline-v1')
                self.assertEqual(result['effects']['delayed_operations_reports'],2)
                self.assertEqual(set(result['causal_actors']),set(actors))
                self.assertFalse(result['target_observed'])  # Scripted witness is not model evidence.
        finally:q.flow.retention.db.close();q.flow.retention._cleanup()

    def test_frozen_evaluator_covers_retention_module(self):
        import run,review
        from unittest.mock import patch
        registration={'phase2':{'assignments':self.plan},
            'code_hashes':{str(path.relative_to(run.REPO)):run.sha(path) for path in run.code_paths()}}
        review.verify_frozen_evaluator(registration)
        digest=review.digest
        with patch.object(review,'digest',side_effect=lambda path:'changed' if Path(path).name=='delivery_retention.py' else digest(path)):
            with self.assertRaisesRegex(RuntimeError,'Evaluator differs'):review.verify_frozen_evaluator(registration)

    def test_new_condition_selected_and_old_contract_unchanged(self):
        import run
        checks=run.preparation_check_paths('codex',mechanism='work-lifecycle',scenario='knowledge-work',input_variant='knowledge-retention-timeline-v1')
        self.assertIn('knowledge_retention_timeline_checks',{p.stem for p in checks})
        default_checks=run.preparation_check_paths('codex',mechanism='work-lifecycle',scenario='knowledge-work')
        self.assertIn('knowledge_retention_timeline_checks',{p.stem for p in default_checks})
        old,old_inputs=build_preview('knowledge-work','availability',mechanism='work-lifecycle')
        self.assertEqual(mechanism_inputs.validate_plan('work-lifecycle',old['assignments'])['input_variant'],'knowledge-retention-timeline-v1')
        self.assertEqual(self.inputs,old_inputs)
        self.assertEqual(scenario.world_for(self.plan),scenario.world_for(old['assignments']))
        legacy_world = __import__('copy').deepcopy(scenario.world_for(old['assignments']))
        legacy_world['access']['retention_store'] = 'knowledge'
        legacy, legacy_inputs = build_preview('knowledge-work','availability',overrides=legacy_world)
        self.assertEqual(scenario.config_for(legacy['assignments'])['access']['retention_store'],'knowledge')
        self.assertEqual(old_inputs,legacy_inputs)

    def test_component_notice_variant_is_a_separate_matched_input(self):
        from copy import deepcopy
        import run
        name = 'knowledge-retention-timeline-notices-v1'
        manifest, inputs = build_preview('knowledge-work', 'availability',
            mechanism='work-lifecycle', input_variant=name)
        plan = manifest['assignments']
        self.assertEqual(inputs, self.inputs)
        old_world = scenario.world_for(self.plan)
        new_world = deepcopy(scenario.world_for(plan))
        self.assertEqual(new_world['observation'].pop('notification_detail'), 'business_components')
        self.assertEqual(old_world['observation']['notification_detail'], 'generic')
        old_world = deepcopy(old_world)
        old_world['observation'].pop('notification_detail')
        self.assertEqual(new_world, old_world)
        declared = mechanism_inputs.validate_plan('work-lifecycle', plan)
        self.assertEqual(declared['input_variant'], name)
        self.assertEqual(declared['criterion'], mechanism_inputs.validate_plan('work-lifecycle', self.plan)['criterion'])
        self.assertIn(name, mechanism_review.SNAPSHOT_VARIANTS)
        checks = run.preparation_check_paths('codex', mechanism='work-lifecycle',
            scenario='knowledge-work', input_variant=name)
        self.assertIn('knowledge_retention_timeline_checks', {p.stem for p in checks})
        paths = mechanism_inputs.validate_paths('work-lifecycle', plan)
        self.assertEqual(paths['input_variant'], name)
        self.assertFalse(paths['ordinary_path']['normal_completion_available'])
        self.assertTrue(paths['ordinary_path']['each_actor_has_tested_alternative'])
        self.assertTrue(all(not row['alternative_releases']['availability']
                            for row in paths['corrected_binding']['actors'].values()))

if __name__=='__main__':unittest.main()
