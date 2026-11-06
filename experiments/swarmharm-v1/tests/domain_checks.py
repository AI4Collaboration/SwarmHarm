"""The current domain catalog must describe actual continuous input bytes."""
import base64
import json
from pathlib import Path
import unittest

from phase2 import delivery_data, unified_delivery as scenario, workload_sources

HERE = Path(__file__).resolve().parents[1]


class DomainScenarioChecks(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((HERE / 'domain-scenarios.json').read_text())

    def test_current_catalog_describes_continuous_work_not_archived_phases(self):
        self.assertEqual(self.catalog['study_mode'], 'unified')
        contract = self.catalog['shared_contract']
        self.assertTrue(contract['one_task_session_and_world'])
        for key in ('phase_transition', 'formation_gate', 'announced_peers', 'supplied_peer_messages'):
            self.assertFalse(contract[key], key)
        self.assertTrue((HERE / self.catalog['source_implementation']).is_file())
        self.assertEqual(self.catalog['source_revision'], workload_sources.REVISION)
        self.assertTrue((HERE / self.catalog['historical_evidence']).is_file())
        self.assertEqual({r['id'] for r in self.catalog['scenarios']}, set(delivery_data.DOMAINS))
        for legacy in ('component_studies', 'current_phase2_adapter', 'phase2_behavior_coverage'):
            self.assertNotIn(legacy, self.catalog)

    def test_each_catalog_entry_has_real_workstation_sources_and_no_supplied_results(self):
        for entry in self.catalog['scenarios']:
            with self.subTest(domain=entry['id']):
                plan = scenario.plan_for('abcd', domain=entry['id'])
                for row in plan.values():
                    row['continuous_workflow'] = True
                subjects = scenario.world_config.subject_inputs(plan)
                for actor, assignment in plan.items():
                    files = subjects['initial_files'][actor]
                    prefix = '/workspace/' + entry['input_directory'] + '/'
                    self.assertTrue(any(path.startswith(prefix) for path in files))
                    manifest = json.loads(base64.b64decode(files['/workspace/source-data.json']))
                    self.assertNotIn('rows', manifest)
                    self.assertEqual(manifest['domain'], entry['id'])
                    self.assertEqual(delivery_data.source_data(assignment), delivery_data.reference_data(assignment))
                    self.assertNotIn('/workspace/communications.json', files)
                self.assertNotIn('phase1', entry)
                self.assertNotIn('phase2', entry)
                self.assertNotIn('status', entry)


if __name__ == '__main__':
    unittest.main()
