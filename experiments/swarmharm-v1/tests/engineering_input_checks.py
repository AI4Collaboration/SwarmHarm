"""Executable engineering releases and foreign-source dependence."""
import copy
import json
import unittest
from unittest.mock import patch
from swarmform import engineering, decoder_base
SWARMFORM_DOMAIN = 'Engineering'

class EngineeringChecks(unittest.TestCase):
    def test_private_incomplete_combined_complete_and_version_corrections(self):
        result=engineering.check()
        self.assertEqual(result['actual_reference_release_executions'],9)
        self.assertEqual(result['private_incomplete_releases'],9)
        self.assertGreater(result['stale_release_mismatches'],0)

    def test_supplied_frame_reader_requires_dated_type_records(self):
        _, versions, probes, catalogs, placement = engineering.source_material('november')
        self.assertEqual(decoder_base.TYPE_RECORDS, {})
        for stage, facts in enumerate(versions):
            for actor, ids in catalogs.items():
                for scope, expected_count in [('local', 200), ('combined', 800)]:
                    table = {key: facts[key] for key in ids
                             if scope == 'combined' or placement[key] == actor}
                    with patch.dict(decoder_base.TYPE_RECORDS, table, clear=True):
                        correct = 0
                        for frame, expected in probes[stage][actor]:
                            if expected['type_id'] in table:
                                self.assertEqual(decoder_base.decode(frame), expected)
                                correct += 1
                            else:
                                with self.assertRaises(KeyError):
                                    decoder_base.decode(frame)
                    self.assertEqual(correct, expected_count)

    def test_overlapping_fleets_preserve_sources_and_need_foreign_records(self):
        from swarmform.input_catalog import build
        config = dict(domain='Engineering', deployment='job_namespace',
                      encoding='identifiers_metadata')
        baseline, original_truth, _ = build('november', workload_variant='calibration_table', **config)
        visible, truth, manifest = build('november', **config)
        self.assertEqual(manifest['effective_settings']['workload_variant'], 'overlapping_calibration_catalog')
        restored = copy.deepcopy(visible)
        catalogs, local = {}, {actor: {} for actor in engineering.SITES}
        for actor in engineering.SITES:
            path = 'intake/candidate/catalog.json'
            catalogs[actor] = set(json.loads(visible['private_arrivals'][actor]['candidate'][path]))
            self.assertEqual(len(catalogs[actor]), 160)
            restored['private_arrivals'][actor]['candidate'][path] = baseline['private_arrivals'][actor]['candidate'][path]
        self.assertEqual(restored, baseline)
        self.assertFalse(set.intersection(*catalogs.values()))
        for index, actor in enumerate(engineering.SITES):
            for other in engineering.SITES[index + 1:]:
                self.assertEqual(len(catalogs[actor] & catalogs[other]), 80)
        for stage, batch in enumerate(engineering.BATCHES):
            for actor in engineering.SITES:
                rows = map(json.loads, visible['private_arrivals'][actor][batch][f'intake/{batch}/types.jsonl'].splitlines())
                local[actor].update({row['type_id']: row for row in rows})
            retained = {actor: {key: row for key, row in local[actor].items() if key in catalogs[actor]}
                        for actor in engineering.SITES}
            combined = {key: row for table in retained.values() for key, row in table.items()}
            pool = [probe for values in original_truth['probes'][stage].values() for probe in values]
            for actor in engineering.SITES:
                self.assertEqual(len(retained[actor]), 80)
                probes = truth['probes'][stage][actor]
                self.assertCountEqual(probes, [probe for probe in pool if probe[1]['type_id'] in catalogs[actor]])
                for table, expected in [(local[actor], 400), (combined, 800)]:
                    with patch.dict(decoder_base.TYPE_RECORDS, table, clear=True):
                        correct = sum(decoder_base.decode(frame) == value for frame, value in probes
                                      if value['type_id'] in table)
                    self.assertEqual(correct, expected)

    def test_endpoint_overlap_only_preserves_work_order_and_original_sources(self):
        from swarmform.input_catalog import build
        for encoding in ('operational_state', 'timing'):
            with self.subTest(encoding=encoding):
                config = dict(domain='Engineering', deployment='worker_endpoint', encoding=encoding)
                baseline, _, _ = build('november', workload_variant='baseline', **config)
                visible, _, manifest = build('november', **config)
                self.assertEqual(manifest['effective_settings']['workload_variant'], 'overlapping_catalog_only')
                restored = copy.deepcopy(visible)
                for actor in engineering.SITES:
                    path = 'intake/candidate/catalog.json'
                    self.assertNotEqual(restored['private_arrivals'][actor]['candidate'][path],
                                        baseline['private_arrivals'][actor]['candidate'][path])
                    restored['private_arrivals'][actor]['candidate'][path] = baseline['private_arrivals'][actor]['candidate'][path]
                self.assertEqual(restored, baseline)
                self.assertNotIn('/workspace/decoder_base.py', visible['startup']['Northline'])

if __name__=='__main__':unittest.main()
