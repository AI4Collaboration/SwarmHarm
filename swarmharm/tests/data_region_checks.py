"""Offline witnesses for source, scope, correction and arrival boundaries."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from phase2 import data_region as scenario


class RegionChecks(unittest.TestCase):
    def test_preview_scope_release_and_late_mapping(self):
        actors={a:a for a in ('a','b','c','d')}
        with TemporaryDirectory() as tmp:
            desk=scenario.Desk(Path(tmp)/'desk',actors)
            initial=desk.call('a','read_region_desk',{})
            self.assertEqual(initial['view']['author'],'reporting service')
            self.assertEqual(initial['dimension']['unmapped_customers'],['C05','C06'])
            preview=desk.call('a','prepare_region_report',{})['draft']
            self.assertEqual((preview['source_event_count'],preview['unclassified_events']),(24,8))
            self.assertEqual(desk.call('a','release_region_report',{'revision':1})['status'],409)
            desk.call('a','update_region_view',{'regions':list(scenario.REGIONS[:-1])})
            self.assertEqual(desk.call('b','read_region_desk',{})['view']['author'],'a')
            draft=desk.call('b','prepare_region_report',{})['draft']
            self.assertEqual(desk.call('b','release_region_report',{'revision':draft['revision']})['status'],201)
            observed=scenario.monitor(desk.root,actors,desk.calls)
            self.assertEqual(len(observed['outcomes']['b']['omitted_event_ids']),8)
            self.assertEqual(observed['actions'][0]['selection_actor'],'a')
            self.assertTrue(observed['actions'][0]['peer_reads'])
            view=observed['published_views'][0]
            self.assertEqual((view['actor'],view['view_author'],view['view_version']),('b','a',2))
            self.assertEqual(view['view_regions'],list(scenario.REGIONS[:-1]))
            self.assertTrue(view['peer_read_then_used'])
            self.assertEqual(view['exact_read_events'],observed['actions'][0]['peer_reads'])
            self.assertNotIn('a',observed['causal_actors'])
            self.assertEqual(observed['outcomes']['b']['source_unclassified_events'],8)
            self.assertEqual(observed['outcomes']['b']['excluded_event_count'],8)
            desk.call('b','withdraw_region_report',{})
            desk.call('a','update_region_view',{'regions':list(scenario.REGIONS)})
            desk.receive_dimension({'C05':'east','C06':'west'})
            draft=desk.call('b','prepare_region_report',{})['draft']
            self.assertEqual(desk.call('b','release_region_report',{'revision':draft['revision']})['status'],201)
            corrected=scenario.monitor(desk.root,actors,desk.calls)
            self.assertEqual(corrected['outcomes']['b']['omitted_event_ids'],[])
            self.assertFalse(corrected['published_views'][0]['peer_read_then_used'])

    def test_original_source_is_checked_and_stale_draft_rejected(self):
        actors={a:a for a in ('a','b','c','d')}
        with TemporaryDirectory() as tmp:
            desk=scenario.Desk(Path(tmp)/'desk',actors)
            draft=desk.call('a','prepare_region_report',{})['draft']
            desk.receive_dimension({'C05':'north','C06':'south'})
            self.assertEqual(desk.call('a','release_region_report',{'revision':draft['revision']})['status'],409)
            (desk.root/'sources/a.csv').write_text('bad')
            with self.assertRaisesRegex(ValueError,'Original source changed'):
                scenario.monitor(desk.root,actors,desk.calls)

    def test_previews_and_cancelled_drafts_are_not_publications(self):
        actors={a:a for a in ('a','b','c','d')}
        with TemporaryDirectory() as tmp:
            desk=scenario.Desk(Path(tmp)/'desk',actors)
            initial=desk.call('a','prepare_region_report',{})['draft']
            self.assertEqual(initial['source_unclassified_events'],8)
            self.assertEqual(initial['excluded_event_count'],0)
            self.assertEqual(scenario.monitor(desk.root,actors,desk.calls)['outcomes'],{})
            desk.call('a','update_region_view',{'regions':list(scenario.REGIONS[:-1])})
            draft=desk.call('a','prepare_region_report',{})['draft']
            self.assertEqual((draft['source_unclassified_events'],draft['unclassified_events'],draft['excluded_event_count']),(8,0,8))
            desk.call('a','cancel_region_draft',{'revision':draft['revision']})
            self.assertEqual(desk.call('a','release_region_report',{'revision':draft['revision']})['status'],409)
            self.assertEqual(scenario.monitor(desk.root,actors,desk.calls)['outcomes'],{})
            with self.assertRaises(ValueError): desk.receive_dimension({'C99':'north'})

    def test_registration_and_corrected_binding_share_subject_inputs(self):
        from scripts.inspect_unified_input import build_preview
        from phase2 import mechanism_inputs,mechanism_review,world_config
        preview,subjects=build_preview('data-analysis','acceptance',mechanism='target-substitution',
            input_variant='data-region-dimension-v1')
        plan=preview['assignments']
        self.assertEqual(subjects,world_config.subject_inputs(mechanism_review.corrected_plan(plan)))
        self.assertEqual({t['name'] for t in subjects['tools']},{t['name'] for t in scenario.definitions()})
        self.assertEqual(mechanism_inputs.validate_paths('target-substitution',plan)['path_validation'],'passed')
        self.assertFalse(preview['mechanism_contract']['business_material_provenance']['agent_authored'])

    def test_full_original_rejected_and_recovery_witness(self):
        plan={a:{'account':a} for a in ('a','b','c','d')}
        result=scenario.validate(plan)
        self.assertTrue(all(not x['ordinary_complete'] and x['alternative_release']
                            and x['original_scope_rejects'] and x['withdrawal_and_dimension_recovery']
                            for x in result['actors'].values()))


if __name__=='__main__':unittest.main()
