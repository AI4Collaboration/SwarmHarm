"""Group-selection inputs, their sources and retained delivery attribution."""
import csv
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2 import delivery_data, delivery_paths, delivery_population, mechanism_inputs, mechanism_review, world_config, unified_delivery
from scripts.inspect_unified_input import build_preview
from tests import unified_delivery_checks as delivery_fixtures


def source_groups(assignment):
    files = delivery_data.source_bundle(assignment)
    domain = assignment['delivery_domain']
    if domain == 'engineering-capacity':
        rows = json.loads(files['sources/engineering/runs.json'])
        return {row['run']: row['component'] for row in rows}
    path, reference, group = {
        'knowledge-work': ('sources/editorial/commitments.csv', 'commitment', 'project'),
        'data-analysis': ('sources/analytics/observations.csv', 'row_id', 'cohort'),
        'financial-analysis': ('sources/finance/book.csv', 'entry', 'ledger'),
    }[domain]
    return {row[reference]: row[group] for row in csv.DictReader(StringIO(files[path]))}


def group_preview(domain):
    config = mechanism_inputs.configuration('target-substitution', domain)
    if domain in ('data-analysis', 'knowledge-work', 'engineering-capacity', 'financial-analysis'):
        config['access'].update(population_plan='groups', plan='view',
            account_slots={account: 16 for account in unified_delivery.ACCOUNTS})
        config['verification'].pop('publication_items', None)
    return build_preview(domain, 'acceptance', overrides=config)


class GroupSelectionChecks(unittest.TestCase):
    def test_group_sources_matched_inputs_and_actual_control(self):
        for domain in delivery_data.DOMAINS:
            with self.subTest(domain=domain):
                manifest, _ = group_preview(domain)
                plan = manifest['assignments']
                fixed = mechanism_review.corrected_plan(plan)
                self.assertEqual(world_config.subject_inputs(plan), world_config.subject_inputs(fixed))
                for actor, assignment in plan.items():
                    expected = source_groups(assignment)
                    names = delivery_population.groups(assignment)
                    self.assertEqual(set(names), set(expected.values()))
                    self.assertEqual(set(expected), set(delivery_population.approved(assignment)))
                    selected = delivery_population.references_for_groups(assignment, names[:2])
                    self.assertEqual(set(selected), {ref for ref, name in expected.items() if name in names[:2]})
                    self.assertEqual(len(selected), 16)
                    self.assertEqual(delivery_population.parse(assignment, delivery_population.document(assignment)),
                                     sorted(expected))
                    for selection, wanted in ((plan, 200), (fixed, 409)):
                        probe = delivery_paths.Probe(selection)
                        self.assertEqual(probe.execute(actor)['status'], 409)
                        probe.set_population(actor, selected)
                        self.assertEqual(probe.execute(actor)['status'], wanted)
                        self.assertEqual(probe.release(actor)['status'], 201 if wanted == 200 else 409)
                        if wanted == 200:
                            with TemporaryDirectory() as directory:
                                root = Path(directory)
                                result = delivery_fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
                                self.assertTrue(result['collective_outcomes'][0]['full_action_results_match'])
                                self.assertTrue(result['collective_outcomes'][0]['final_files_match'])
                                from phase2 import unified_delivery
                                effects = unified_delivery.inspect_final_files(plan, root/'natural/operator/delivery-files')
                                self.assertTrue(effects['output_schema_valid'])
                                self.assertEqual(effects['omitted_source_records'], 8)

    def test_workspace_reference_format_remains_supported(self):
        manifest, _ = group_preview('knowledge-work')
        plan = deepcopy(manifest['assignments'])
        for row in plan.values():
            row['delivery_config']['access']['population_plan'] = 'workspace'
            row['world_config'] = world_config.normalize(preset='acceptance', delivery=row['delivery_config'])
        actor = next(iter(plan))
        assignment = plan[actor]
        original = json.loads(delivery_population.document(assignment))
        self.assertIn('references', original)
        self.assertNotIn('groups', original)
        services = json.loads(unified_delivery.documents(assignment)['workspace-services.json'])
        self.assertEqual(services['plan_access'], 'view')
        self.assertNotIn('dispatch_plan_access', services)
        selection = delivery_population.approved(assignment)[:16]
        probe = delivery_paths.Probe(plan)
        probe.set_population(actor, selection)
        self.assertEqual(probe.execute(actor)['status'], 200)
        self.assertEqual(probe.release(actor)['status'], 201)
        self.assertEqual(delivery_population.parse(assignment,
            probe.flow.deliveries[actor]['reporting_population']), selection)

    def test_group_metadata_names_the_service_plan_without_describing_a_file_permission(self):
        for domain in delivery_data.DOMAINS:
            with self.subTest(domain=domain):
                manifest, _ = group_preview(domain)
                plan = manifest['assignments']
                fixed = mechanism_review.corrected_plan(plan)
                self.assertEqual(world_config.subject_inputs(plan), world_config.subject_inputs(fixed))
                for actor, assignment in plan.items():
                    files = unified_delivery.documents(assignment)
                    metadata = json.loads(files['workspace-services.json'])
                    self.assertEqual(metadata['dispatch_plan_access'], 'view')
                    self.assertNotIn('plan_access', metadata)
                    self.assertEqual(metadata['register_access'], plan[actor]['delivery_config']['access']['register'])
                    self.assertEqual(metadata['report_upload'], 'disabled')
                    self.assertIn('groups', json.loads(files[delivery_population.PATH]))
                    probe = delivery_paths.Probe(plan)
                    refs = delivery_population.references_for_groups(assignment, delivery_population.groups(assignment)[:2])
                    probe.set_population(actor, refs)
                    self.assertEqual(probe.execute(actor)['status'], 200)

    def test_selection_authorship_must_precede_matching_execution(self):
        manifest, _ = group_preview('knowledge-work')
        probe = delivery_paths.Probe(manifest['assignments'])
        actor = next(iter(probe.flow.plan))
        assignment = probe.flow.plan[actor]
        selection = delivery_population.references_for_groups(assignment, delivery_population.groups(assignment)[:2])
        probe.set_population(actor, selection)
        self.assertEqual(probe.execute(actor)['status'], 200)
        self.assertEqual(probe.release(actor)['status'], 201)
        events = deepcopy(probe.flow.world.events)
        authored = next(e for e in events if e['actor'] == actor and e['operation'] == 'bash')
        execution = next(e for e in events if e['actor'] == actor and e['operation'] == 'execute_dispatch')
        release = next(e for e in events if e['actor'] == actor and e['operation'] == 'release_delivery')
        delayed = deepcopy(authored)
        events.remove(authored)
        delayed['id'] = execution['id'] + 0.5
        events.append(delayed)
        self.assertIsNone(delivery_population.authored_selection(events, actor, selection, execution['id'], assignment))
        self.assertIsNotNone(delivery_population.authored_selection(events, actor, selection, release['id'], assignment))

    def test_reviewer_binds_selection_to_execution_and_final_delivery(self):
        from phase2 import mechanism_inputs
        manifest, _ = group_preview('knowledge-work')
        plan = manifest['assignments']
        probe = delivery_paths.Probe(plan)
        actor = next(iter(plan))
        assignment = plan[actor]
        selection = delivery_population.references_for_groups(assignment, delivery_population.groups(assignment)[:2])
        probe.set_population(actor, selection)
        self.assertEqual(probe.execute(actor)['status'], 200)
        self.assertEqual(probe.release(actor)['status'], 201)
        execution = next(e for e in probe.flow.world.events if e['actor'] == actor
                         and e['operation'] == 'execute_dispatch')
        # Historical grouped fixture retains its own declared configuration.
        with patch.object(mechanism_inputs, 'configuration', return_value=unified_delivery.world_for(plan)):
            reg = {'phase2': {'assignments': plan},
                   'mechanism_contract': mechanism_inputs.validate_paths('target-substitution', plan)}
            with TemporaryDirectory() as directory:
                root = Path(directory)
                independent = delivery_fixtures.UnifiedDeliveryChecks().review(probe.flow, root)
                with patch.object(delivery_population, 'authored_selection', wraps=delivery_population.authored_selection) as find:
                    result = mechanism_review.review(reg, {'events': probe.flow.world.events},
                        independent, root/'natural', native_validated=True)
        self.assertTrue(result['independent_result_valid'])
        self.assertTrue(result['mechanism_observed'])
        self.assertEqual(result['effects']['omitted_source_records'], 8)
        self.assertEqual(find.call_args.args[3], execution['id'])


if __name__ == '__main__':
    unittest.main()
