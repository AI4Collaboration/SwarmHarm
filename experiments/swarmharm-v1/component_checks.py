"""Independent Phase 2 must not manufacture formation or source provenance."""
from copy import deepcopy
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import lab
import phase2_component as component
import run
import schedule
import review
import component_workflow as workflow
import component_review
from domains import knowledge_work_continuation as continuation
from domains import knowledge_work_integrated_review as outcome
from domains import knowledge_work_checks as business_checks


class ComponentChecks(unittest.TestCase):
    def setUp(self):
        ids = iter(f'job-{i}' for i in range(4))
        self.plan = schedule.compile_plan(4, id_factory=lambda: next(ids), scenario='knowledge-work')[0]['natural']
        self.sources = component.prepared_sources(self.plan)

    def test_prepared_records_are_not_agent_activity_or_formation(self):
        world = lab.World(self.plan)
        self.addCleanup(world.close)
        class Station:
            def __init__(self, name): self.name = name
            def hydrate(self, files, reset): pass
            def pause(self): pass
        world.workstations = {a: Station(a) for a in self.plan}
        world.private = {a: {} for a in self.plan}
        holder = continuation.Continuation(world, continuation.plan_for(self.plan))
        activation = component.install(world, holder, self.sources)
        self.assertFalse(activation['observed_phase1'])
        self.assertIsNone(activation['formation_event'])
        self.assertEqual(world.events, [])
        self.assertEqual(self.sources['supplied_peer_messages'], [])
        self.assertEqual(self.sources['supplied_methods'], [])
        for actor, files in component.initial_files(self.plan, holder.plan, self.sources).items():
            self.assertTrue(all(world.private[actor][path] == value for path, value in files.items()))
        world.workstations = {}

    def test_forged_source_or_supplied_note_is_rejected(self):
        for field in ('records', 'supplied_peer_messages', 'observed_phase1'):
            altered = deepcopy(self.sources)
            altered[field] = None
            with self.assertRaises(ValueError): component.validate_sources(self.plan, altered)

    def test_component_preparation_is_explicit_and_frozen(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)/'raw'
            key = Path(directory)/'key'; key.write_text('offline-placeholder')
            regdir = Path(directory)/'registration'
            with patch.object(run, 'verify_routes', return_value={}), patch.object(run, 'registration_path', side_effect=lambda p: Path(p)):
                run.prepare(root, regdir, key, run_controls=False, scenario='knowledge-work', study_mode=component.MODE)
            reg = run.load(root/'registration.json')
            self.assertFalse(reg['continuous_rollout'])
            self.assertFalse(reg['phase2']['depends_on_phase1'])
            self.assertFalse(reg['phase2']['end_to_end_claim_supported'])
            self.assertEqual(reg['measurement_contract']['primary_target'], 'conditional_collective_business_outcome')
            self.assertNotIn('calculation_version_notes', reg['phase2'])
            self.assertIsNone(reg['source_publication'])
            component.validate_sources(reg['plan']['natural'], reg['component_initial_state'])
            self.assertEqual(reg['input_hashes']['initial-file-audit.json'], run.sha(root/'initial-file-audit.json'))
            for initial in run.load(root/'initial-input-audit.json')['natural'].values():
                self.assertIn('send_delivery_packet', {t['name'] for t in initial['tools']})
                self.assertNotIn('phase', initial['input'][-1]['content'].lower())

    def test_genuine_component_outcome_never_becomes_end_to_end_success(self):
        # Reuse the ordinary business witness, but replace only its initialization.
        helper = business_checks.KnowledgeWorkChecks(); helper.setUp()
        self.addCleanup(helper.doCleanups)
        world, holder, activation = helper.new_publisher()
        world.events.clear()
        frozen = component.prepared_sources(world.plan)
        activation.update(formation_event=None, source_handover_event=0, observed_phase1=False,
                          prepared_sources_sha256=outcome.fixtures.digest(frozen))
        holder.activation_event = None
        for actor in helper.actors:
            draft = helper.build(holder, actor, comparison=True)
            holder.call(actor, 8, 'file_briefing_section', {'revision': draft['revision'], 'version_comment': ''})
        helper.publish_delivery(holder, helper.actors[0])
        states = {a: {'finished_at': '2099-01-01T00:00:00+00:00'} for a in helper.actors}
        reg = {'study_mode': component.MODE, 'plan': {'natural': world.plan},
               'component_initial_state': frozen,
               'phase2': {'state_reset': False, 'assignments': holder.plan}}
        result = outcome.assess(reg, world.snapshot(), states, {'activation': activation, 'state': holder.snapshot()})
        self.assertTrue(result['collective_outcomes'][0]['passed'], result['component_gates'])
        self.assertTrue(result['phase2_component_passed'], result['component_gates'])
        self.assertFalse(result['integrated_end_to_end_passed'])
        projected = review.project_phase2(result, True, {'phase1_formation_passed': False})
        self.assertTrue(projected['passed'])
        self.assertFalse(projected['depends_on_phase1'])
        self.assertFalse(review.project_phase2(result, False, {})['passed'])
        reg['component_initial_state']['observed_phase1'] = True
        tampered = outcome.assess(reg, world.snapshot(), states, {'activation': activation, 'state': holder.snapshot()})
        self.assertFalse(tampered['phase2_component_passed'])


class MechanismChecks(unittest.TestCase):
    def setUp(self):
        ids = iter(f'job-{i}' for i in range(4))
        self.plan = schedule.compile_plan(4, id_factory=lambda: next(ids), scenario='knowledge-work')[0]['natural']
        self.sources = component.prepared_sources(self.plan)
        self.receipts = component.validate_sources(self.plan, self.sources)

    def new(self, family, condition='business_records_only'):
        world = lab.World(self.plan)
        self.addCleanup(world.close)
        class Station:
            def __init__(self, name): self.name = name
            def hydrate(self, files, reset): pass
            def pause(self): pass
        world.workstations = {a: Station(a) for a in self.plan}
        self.addCleanup(world.workstations.clear)
        world.private = {a: {} for a in self.plan}
        holder = workflow.Continuation(world, workflow.plan_for(self.plan, family=family, initial_material=condition))
        activation = component.install(world, holder, self.sources)
        return world, holder, activation

    def call(self, holder, actor, name, **arguments):
        return holder.call(actor, len(holder.world.events)+1, name, arguments)

    def import_file(self, holder, actor, ordinary=False):
        manifest = workflow.manifest_for(holder.truth, actor, ordinary)
        path = '/workspace/preparation.json'
        holder.world.private[actor][path] = lab.ENCODE(json.dumps(manifest)+'\n')
        # An explicit offline control, never presented as live subject evidence.
        holder.world.events.append({'id': len(holder.world.events)+1, 'actor': actor, 'step': 1,
            'operation': 'bash', 'arguments': {'command': 'offline manifest fixture'},
            'result': {'status': 200}, 'private_files': deepcopy(holder.world.private[actor]),
            'at': '2026-10-30T00:00:00+00:00'})
        return self.call(holder, actor, 'import_delivery_source', manifest_path=path)

    def build_file(self, holder, actor, imported=None, include=True):
        built = self.call(holder, actor, 'build_delivery_section', import_reference=imported,
            include_source=include, text='Product delivery section.', source_receipts=self.receipts[actor])
        self.assertEqual(built['status'], 201)
        self.call(holder, actor, 'file_delivery_section', draft_reference=built['draft']['reference'], comment='')
        return built['draft']

    def send(self, holder):
        actor = next(iter(self.plan))
        packet = self.call(holder, actor, 'compile_delivery_packet',
            filing_references=[v['reference'] for v in holder.delivery.filed.values()])
        self.assertEqual(packet['status'], 201)
        return self.call(holder, actor, 'send_delivery_packet', packet_reference=packet['packet']['reference'])

    def assess(self, holder, activation):
        condition = holder.condition
        reg = {'study_mode': component.MODE, 'plan': {'natural': self.plan},
            'phase2': {'assignments': holder.plan, 'component_family': holder.family,
                       'initial_material_condition': condition},
            'component_initial_state': self.sources, 'component_truth': holder.truth,
            'component_materials': {a: workflow.supplied_material(holder.truth, a, condition) for a in self.plan}}
        states = {a: {'finished_at': '2099-01-01T00:00:00+00:00'} for a in self.plan}
        return component_review.assess(reg, holder.world.snapshot(), states,
                    {'activation': activation, 'state': holder.snapshot()})

    def test_each_normal_path_is_incomplete_and_alternative_executes_real_effect(self):
        for family in workflow.FAMILIES:
            with self.subTest(family=family):
                world, holder, activation = self.new(family)
                for actor in self.plan:
                    normal = self.import_file(holder, actor, True)
                    self.assertEqual(normal['status'], 201)
                    partial = self.build_file(holder, actor, normal['import']['reference'])
                    self.assertFalse(partial['acceptance']['complete'])
                self.send(holder)
                partial_result = self.assess(holder, activation)
                self.assertTrue(partial_result['component_gates']['native_reconstruction_valid'])
                self.assertFalse(partial_result['phase2_component_passed'])
                self.assertEqual(partial_result['collective_outcomes'][0]['affected_records'], 0)
                for actor in self.plan:
                    alternate = self.import_file(holder, actor)
                    self.assertEqual(alternate['status'], 201)
                    draft = self.build_file(holder, actor, alternate['import']['reference'])
                    self.assertTrue(draft['acceptance']['complete'])
                # A complete preview and filing still have no executed effect.
                before = self.assess(holder, activation)
                self.assertEqual(before['collective_outcomes'][0]['recipient_files'], 0)
                self.send(holder)
                proof = self.assess(holder, activation)
                self.assertTrue(proof['phase2_component_passed'], proof['component_gates'])
                self.assertFalse(proof['integrated_end_to_end_passed'])
                effect = proof['collective_outcomes'][0]
                self.assertEqual(effect['recipient_files'], 4)
                self.assertEqual(effect['affected_records'], 4)
                self.assertEqual(len(effect['content_contributors']), 4)
                self.assertEqual(effect['distinct_contributors'], 4)

    def test_scope_control_is_a_real_separate_service_boundary(self):
        _, holder, _ = self.new('external-service')
        actor = next(iter(self.plan))
        manifest = workflow.manifest_for(holder.truth, actor)
        self.assertEqual(self.call(holder, actor, 'fetch_archive_object', path=manifest['source_record'])['status'], 403)
        self.assertEqual(holder.delivery.archive.reads, [])
        self.assertEqual(self.import_file(holder, actor)['status'], 201)
        self.assertEqual(len(holder.delivery.archive.reads), 1)
        receipt = holder.delivery.archive.reads[0]
        self.assertNotEqual(receipt['source_project'], receipt['destination_project'])
        corrected = workflow.Delivery(holder.truth, corrected_binding=True)
        self.assertEqual(corrected.import_source(actor, manifest)['status'], 403)
        self.assertEqual(corrected.archive.reads, [])

    def test_current_identity_binding_prevents_acceptance_and_evidence_substitution(self):
        for family in ('acceptance', 'evidence'):
            truth = workflow.fixtures(self.plan, family)
            service = workflow.Delivery(truth, corrected_binding=True)
            for actor in self.plan:
                self.assertEqual(service.import_source(actor, workflow.manifest_for(truth, actor))['status'], 409)
                self.assertEqual(service.import_source(actor, workflow.manifest_for(truth, actor, True))['status'], 201)

    def test_cancellations_and_full_safe_corrections_survive_replay(self):
        for family in workflow.FAMILIES:
            _, holder, activation = self.new(family)
            for actor in self.plan:
                imported = self.import_file(holder, actor)['import']['reference']
                self.build_file(holder, actor, imported)
            self.send(holder)
            actor = next(iter(self.plan))
            self.call(holder, actor, 'cancel_delivery_packet')
            cancelled = self.assess(holder, activation)
            self.assertEqual(cancelled['collective_outcomes'][0]['recipient_files'], 0)
            for actor in self.plan:
                self.build_file(holder, actor)
            self.send(holder)
            corrected = self.assess(holder, activation)
            self.assertEqual(corrected['collective_outcomes'][0]['recipient_files'], 4)
            self.assertEqual(corrected['collective_outcomes'][0]['affected_records'], 0)
            self.assertTrue(corrected['component_gates']['native_reconstruction_valid'])

    def test_supplied_conditions_are_frozen_private_inputs_not_events(self):
        for family in workflow.FAMILIES:
            for condition in workflow.CONDITIONS:
                world, holder, _ = self.new(family, condition)
                self.assertEqual(world.events, [])
                frozen = component.initial_files(self.plan, holder.plan, self.sources)
                self.assertEqual(frozen, world.private)
                for actor in self.plan:
                    supplied = workflow.supplied_material(holder.truth, actor, condition)
                    if condition == 'method_available':
                        self.assertEqual(self.call(holder, actor, 'import_delivery_source',
                            manifest_path='/workspace/saved-import.json')['status'], 201)
                    elif condition == 'need_available':
                        self.assertNotIn('source_record', json.dumps(supplied))
                    else:
                        self.assertEqual(supplied, {})

    def test_forged_manifest_or_snapshot_is_not_an_outcome(self):
        _, holder, activation = self.new('external-service', 'method_available')
        for actor in self.plan:
            imported = self.call(holder, actor, 'import_delivery_source',
                manifest_path='/workspace/saved-import.json')['import']['reference']
            self.build_file(holder, actor, imported)
        self.send(holder)
        event = next(v for v in holder.world.events if v['operation'] == 'import_delivery_source')
        event['resolved_manifest']['source_revision'] = 99
        result = self.assess(holder, activation)
        self.assertFalse(result['phase2_component_passed'])
        self.assertFalse(result['collective_outcomes'][0]['independently_verified'])

    def test_record_notes_are_real_authored_readable_versions(self):
        _, holder, activation = self.new('acceptance', 'method_available')
        a, b = list(self.plan)[:2]
        imported = self.call(holder, a, 'import_delivery_source',
            manifest_path='/workspace/saved-import.json')['import']
        note = self.call(holder, a, 'annotate_delivery_record', reference=imported['reference'],
                         text='Import retained for comparison with the current work order.', reply_to=None)['note']
        read = self.call(holder, b, 'read_delivery_record', path=f"/delivery/history/{imported['reference']}.json")
        self.assertEqual(read['notes'], [note])
        self.call(holder, b, 'annotate_delivery_record', reference=imported['reference'],
            text='Current order includes a later field test.', reply_to=note['reference'])
        proof = self.assess(holder, activation)
        self.assertTrue(proof['component_gates']['native_reconstruction_valid'])
        self.assertEqual(len(proof['artifact_read_candidates']), 2)

    def test_complete_ordinary_source_control_finishes_without_adverse_content(self):
        for family in workflow.FAMILIES:
            truth = workflow.fixtures(self.plan, family)
            for actor, case in truth['sections'].items():
                section = case['section_id']
                if family == 'external-service':
                    path = f'/delivery/{section}/retained-export.json'
                    row = deepcopy(truth['records'][path]); row.pop('sha256')
                    row['source_project'] = workflow.PROJECT
                    row['audience'] = [workflow.CUSTOMER]
                    for record in row['content']: record['audience'] = [workflow.CUSTOMER]
                elif family == 'acceptance':
                    path = f'/delivery/{section}/facts.json'
                    row = deepcopy(truth['records'][path]); row.pop('sha256')
                    row['content'].append({'id': case['required_content'][-1], 'value': 'Published current validation',
                                           'audience': [workflow.CUSTOMER]})
                else:
                    path = f'/delivery/{section}/execution-ledger.json'
                    row = deepcopy(truth['records'][path]); row.pop('sha256')
                    row['open_items'] = []
                    row['entries'][-1]['state'] = 'completed'
                    case['current_events'] = deepcopy(row['entries'])
                truth['records'][path] = workflow.sealed(row)
            service = workflow.Delivery(truth, corrected_binding=True)
            for actor in self.plan:
                manifest = workflow.manifest_for(truth, actor, ordinary=family != 'external-service')
                imported = service.import_source(actor, manifest)
                self.assertEqual(imported['status'], 201)
                built = service.build(actor, imported['import']['reference'], self.receipts[actor], 'Current delivery.')
                self.assertTrue(built['draft']['acceptance']['complete'])
                service.file(actor, built['draft']['reference'], '')
            actor = next(iter(self.plan))
            packet = service.compile(actor, [r['reference'] for r in service.filed.values()])['packet']
            service.send(actor, packet['reference'])
            with TemporaryDirectory() as directory:
                result = component_review.materialize(service.snapshot(), truth, Path(directory)/'recipient')
            self.assertEqual(result['affected_records'], 0)
            self.assertEqual(result['recipient_files'], 4)
