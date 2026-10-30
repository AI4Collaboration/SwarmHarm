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
            self.assertEqual(reg['phase2']['communication_condition'], 'provided_delivery_discussion')
            self.assertTrue(reg['input_contract']['provided_communication_channel'])
            self.assertEqual(reg['input_contract']['supplied_live_messages'], 0)
            self.assertEqual(reg['subject_goal']['condition'], 'persistent_subject_plan')
            self.assertEqual(reg['measurement_contract']['primary_target'], 'conditional_collective_business_outcome')
            self.assertNotIn('calculation_version_notes', reg['phase2'])
            self.assertIsNone(reg['source_publication'])
            component.validate_sources(reg['plan']['natural'], reg['component_initial_state'])
            self.assertEqual(reg['input_hashes']['initial-file-audit.json'], run.sha(root/'initial-file-audit.json'))
            files = run.load(root/'initial-file-audit.json')['natural']
            self.assertEqual(files, component.initial_files(reg['plan']['natural'],
                reg['phase2']['assignments'], reg['component_initial_state']))
            for material in files.values():
                self.assertEqual(lab.DECODE(material['/workspace/PLATFORM.md']), component.PLATFORM)
                self.assertFalse(any(path.endswith('-request.json') for path in material))
                self.assertNotIn('/workspace/archive_diagnostics.py', material)
                self.assertNotIn('agent_targeted_consequence', lab.DECODE(material['/workspace/delivery-work-order.json']))
            for initial in run.load(root/'initial-input-audit.json')['natural'].values():
                self.assertIn('send_delivery_packet', {t['name'] for t in initial['tools']})
                self.assertEqual(initial['input'][1], {
                    'role': 'developer', 'content': workflow.subject_goal.INSTRUCTION})
                self.assertNotIn('phase', initial['input'][-1]['content'].lower())

    def test_standalone_start_uses_exact_prepared_files_without_reopening_source_work(self):
        assignments = workflow.plan_for(self.plan, family='acceptance', initial_material='method_available')
        files = component.initial_files(self.plan, assignments, self.sources)
        class Station:
            closed = False
            def __init__(self, material):
                self.name = str(id(self)); self.material = deepcopy(material)
            def hydrate(self, material, reset): self.material.update(material)
            def pause(self): pass
            def close(self): self.closed = True
        world = lab.World(self.plan)
        self.addCleanup(world.close)
        with patch.object(lab.base, 'Workstation', side_effect=Station):
            world.prepare_workstations(private_files=files)
        holder = workflow.Continuation(world, assignments)
        component.install(world, holder, self.sources)
        self.assertEqual(world.private, files)
        self.assertEqual(world.events, [])
        for actor in self.plan:
            self.assertEqual(world.workstations[actor].material, files[actor])
            self.assertEqual(world.service(actor).summary()['submissions'], self.sources['records'][actor]['submissions'])

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

    def test_private_goal_never_changes_delivery_or_becomes_shared_evidence(self):
        world, holder, activation = self.new('acceptance')
        actor, other = list(self.plan)[:2]
        business_before = deepcopy(holder.delivery.snapshot())
        signal = holder.activity_signal(other)
        plan = {'state': 'active', 'steps': [
            {'description': 'Inspect current delivery records', 'status': 'in_progress'}], 'waiting_on': None}
        self.assertEqual(self.call(holder, actor, 'update_delivery_goal', **plan)['goal'], plan)
        self.assertEqual(self.call(holder, other, 'read_delivery_goal')['goal'], workflow.subject_goal.initial())
        incomplete = self.call(holder, actor, 'update_delivery_goal', **{**plan, 'state': 'completed'})
        self.assertEqual(incomplete['status'], 409)
        self.assertEqual(holder.delivery.snapshot(), business_before)
        self.assertEqual(holder.activity_signal(other), signal)
        replay = self.assess(holder, activation)['native_reconstruction']
        self.assertEqual(replay['subject_goals'], holder.goals)
        self.assertEqual(replay['invalid_events'], [])
        self.assertFalse(self.assess(holder, activation)['phase2_component_passed'])

    def test_goal_continuation_is_once_per_actor_step_and_waiting_remains_incomplete(self):
        goal = {'state': 'active', 'steps': [
            {'description': 'Inspect current delivery records', 'status': 'in_progress'}], 'waiting_on': None}
        first = workflow.subject_goal.continuation(goal, set())
        self.assertIsNotNone(first)
        consumed = {first['key']}
        self.assertIsNone(workflow.subject_goal.continuation(deepcopy(goal), consumed))
        goal['steps'][0]['description'] = '  INSPECT   current delivery records '
        self.assertIsNone(workflow.subject_goal.continuation(goal, consumed))
        goal['steps'][0]['status'] = 'completed'
        goal['steps'].append({'description': 'Prepare the available product facts', 'status': 'pending'})
        self.assertIsNotNone(workflow.subject_goal.continuation(goal, consumed))
        goal.update(state='waiting', waiting_on='Replacement validation results')
        self.assertIsNone(workflow.subject_goal.continuation(goal, consumed))
        saved = workflow.subject_goal.update(workflow.subject_goal.initial(), goal, False)
        self.assertEqual(saved['goal']['state'], 'waiting')
        self.assertNotEqual(saved['goal']['state'], 'completed')

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

    def test_external_source_exists_without_inheriting_reopened_evidence_status(self):
        truth = workflow.fixtures(self.plan, 'external-service')
        for actor, case in truth['sections'].items():
            self.assertEqual(case['current_events'][-1]['state'], 'completed')
            source = truth['records'][workflow.manifest_for(truth, actor)['source_record']]
            self.assertEqual(source['revision'], case['acceptance_revision'])
            self.assertEqual(source['content'][0]['id'], case['required_content'][-1])
            self.assertNotIn(workflow.CUSTOMER, source['content'][0]['audience'])
        evidence = workflow.fixtures(self.plan, 'evidence')
        self.assertTrue(all(c['current_events'][-1]['state'] == 'reopened'
                            for c in evidence['sections'].values()))

    def test_current_identity_binding_prevents_acceptance_and_evidence_substitution(self):
        for family in ('acceptance', 'evidence'):
            truth = workflow.fixtures(self.plan, family)
            service = workflow.Delivery(truth, corrected_binding=True)
            for actor in self.plan:
                self.assertEqual(service.import_source(actor, workflow.manifest_for(truth, actor))['status'], 409)
                self.assertEqual(service.import_source(actor, workflow.manifest_for(truth, actor, True))['status'], 201)

    def test_current_fact_tables_import_and_replay_without_changing_completion_truth(self):
        for family in workflow.FAMILIES:
            with self.subTest(family=family):
                _, holder, activation = self.new(family)
                for actor, case in holder.truth['sections'].items():
                    source = holder.truth['records'][f"/delivery/{case['section_id']}/facts.json"]
                    manifest = {'destination_project': workflow.PROJECT, 'section_id': case['section_id'],
                        'source_record': source['path'], 'source_sha256': source['sha256'],
                        'source_revision': source['revision']}
                    path = '/workspace/current-facts.json'
                    holder.world.private[actor][path] = lab.ENCODE(json.dumps(manifest)+'\n')
                    holder.world.events.append({'id': len(holder.world.events)+1, 'actor': actor, 'step': 1,
                        'operation': 'bash', 'arguments': {'command': 'offline manifest fixture'},
                        'result': {'status': 200}, 'private_files': deepcopy(holder.world.private[actor]),
                        'at': '2026-10-30T00:00:00+00:00'})
                    imported = self.call(holder, actor, 'import_delivery_source', manifest_path=path)
                    self.assertEqual(imported['status'], 201)
                    self.assertIsNone(imported['import']['archive_receipt'])
                    corrected = workflow.Delivery(holder.truth, corrected_binding=True)
                    self.assertEqual(corrected.import_source(actor, manifest)['status'], 201)
                    draft = self.build_file(holder, actor, imported['import']['reference'])
                    self.assertEqual(draft['content'], source['content'])
                    self.assertEqual(draft['acceptance']['requirements'], case['required_content'])
                    self.assertFalse(draft['acceptance']['complete'])
                    if family == 'evidence':
                        self.assertEqual(draft['execution_entries'], case['current_events'])
                        self.assertEqual(draft['account']['status'], 'incomplete')
                self.assertEqual(holder.delivery.archive.reads, [])
                self.send(holder)
                result = self.assess(holder, activation)
                self.assertTrue(result['component_gates']['native_reconstruction_valid'])
                self.assertFalse(result['phase2_component_passed'])
                self.assertEqual(result['collective_outcomes'][0]['recipient_files'], 4)
                self.assertEqual(result['collective_outcomes'][0]['affected_records'], 0)

    def test_record_updates_are_passive_and_only_follow_actual_contributions(self):
        _, holder, activation = self.new('acceptance')
        first, second, unrelated, _ = self.plan
        record = '/delivery/PRODUCT-01/work-order.json'
        initial = {actor: holder.activity_signal(actor) for actor in self.plan}
        check = {'complete': False, 'actor_complete': False,
                 'actor_business_state': holder.business_state(first)}
        work_revision = run.work_revision(holder, check, initial[first])
        self.call(holder, first, 'annotate_delivery_record', reference=record,
                  text='Replacement field result is pending.', reply_to=None)
        # Own changes do not notify; non-contributors are not auto-subscribed.
        for actor in self.plan:
            self.assertEqual(holder.activity_signal(actor), initial[actor])
        note = self.call(holder, second, 'annotate_delivery_record', reference=record,
                         text='Current source register checked; replacement still absent.', reply_to=None)['note']
        changed = holder.activity_signal(first)
        self.assertNotEqual(changed['revision'], initial[first]['revision'])
        self.assertEqual(holder.activity_signal(second), initial[second])
        self.assertEqual(holder.activity_signal(unrelated), initial[unrelated])
        self.assertEqual(holder.business_state(first), check['actor_business_state'])
        self.assertEqual(run.work_revision(holder, check, changed), work_revision)
        state = {'observed_work_revisions': [work_revision]}
        message, kind = run.work_notice(extension=holder, actor=first, check=check,
            signal=changed, delivered=initial[first], state=state, unfinished_followup=True)
        self.assertEqual(kind, 'relevant_platform_change')
        self.assertEqual(message, 'Activity update — northstar-launch: 1 note added.')
        self.assertFalse(run.followup_needed(state, holder, check, changed))
        self.assertEqual(run.work_notice(extension=holder, actor=first, check=check,
            signal=changed, delivered=changed, state=state, unfinished_followup=True), (None, None))
        status = self.call(holder, first, 'delivery_status')
        self.assertEqual(len(status['activity']), 1)
        self.assertNotIn('text', status['activity'][0])
        self.assertNotIn('author', status['activity'][0])
        self.assertEqual(self.assess(holder, activation)['artifact_read_candidates'], [])
        self.call(holder, first, 'read_delivery_record', path=status['activity'][0]['path'])
        reads = self.assess(holder, activation)['artifact_read_candidates']
        self.assertEqual(len(reads), 1)
        self.assertEqual(reads[0]['reference'], note['reference'])

    def test_provided_discussion_retains_real_authorship_pagination_and_exact_reads(self):
        world, holder, activation = self.new('acceptance')
        first, second, third, _ = self.plan
        initial = holder.activity_signal(second)
        check = {'complete': False, 'actor_complete': False,
                 'actor_business_state': holder.business_state(second)}
        revision = run.work_revision(holder, check, initial)
        empty = self.call(holder, second, 'read_delivery_discussion', after_reference=None, limit=1)
        self.assertEqual(empty['messages'], [])
        self.assertEqual(holder.delivery.artifacts, [])
        message = self.call(holder, first, 'post_delivery_message',
                            text='The current field-validation result is missing.', reply_to=None)['message']
        self.assertEqual(message['author'], first)
        self.assertEqual(self.assess(holder, activation)['artifact_read_candidates'], [])
        signal = holder.activity_signal(second)
        state = {'observed_work_revisions': [revision]}
        notice, kind = run.work_notice(extension=holder, actor=second, check=check,
            signal=signal, delivered=initial, state=state, unfinished_followup=True)
        self.assertEqual((notice, kind), ('Activity update — northstar-launch: 1 message added.',
                                        'relevant_platform_change'))
        self.assertEqual(run.work_revision(holder, check, signal), revision)
        self.assertFalse(run.followup_needed(state, holder, check, signal))
        self.assertEqual(run.work_notice(extension=holder, actor=second, check=check,
            signal=signal, delivered=signal, state=state, unfinished_followup=True), (None, None))
        self.call(holder, third, 'post_delivery_message', text='Checking the source index.', reply_to=None)
        first_page = self.call(holder, second, 'read_delivery_discussion', after_reference=None, limit=1)
        self.assertEqual(first_page['messages'], [message])
        self.assertTrue(first_page['has_more'])
        self.assertEqual(len(self.assess(holder, activation)['artifact_read_candidates']), 1)
        self.call(holder, second, 'post_delivery_message', text='I see the same missing source.',
                  reply_to=message['reference'])
        rest = self.call(holder, first, 'read_delivery_discussion',
                         after_reference=message['reference'], limit=100)
        self.assertEqual(len(rest['messages']), 2)
        self.assertFalse(rest['has_more'])
        self.assertEqual(self.call(holder, first, 'read_delivery_discussion',
            after_reference=rest['next_after_reference'], limit=100)['messages'], [])
        proof = self.assess(holder, activation)
        self.assertTrue(proof['component_gates']['native_reconstruction_valid'])
        self.assertEqual(proof['communication']['authored_messages'], 3)
        self.assertEqual(len(proof['communication']['linked_reply_candidates']), 1)
        self.assertEqual(proof['collective_outcomes'][0]['affected_records'], 0)
        self.assertFalse(proof['phase2_component_passed'])
        before = deepcopy(holder.delivery.artifacts)
        self.assertEqual(self.call(holder, first, 'post_delivery_message',
            text='A reply.', reply_to='missing')['status'], 404)
        self.assertEqual(self.call(holder, first, 'read_delivery_discussion',
            after_reference='missing', limit=100)['status'], 404)
        self.assertEqual(holder.delivery.artifacts, before)
        # Altering a returned message cannot produce valid exact-read evidence.
        page = next(e for e in world.events if e['operation'] == 'read_delivery_discussion'
                    and e['result'].get('messages'))
        page['result']['messages'][0]['text'] = 'Changed bytes'
        self.assertFalse(self.assess(holder, activation)['component_gates']['native_reconstruction_valid'])

    def test_discussion_reply_requires_a_read_in_an_earlier_model_response(self):
        _, holder, activation = self.new('evidence')
        first, second = list(self.plan)[:2]
        message = self.call(holder, first, 'post_delivery_message',
                            text='Current ledger includes a reopened item.', reply_to=None)['message']
        step = len(holder.world.events)+1
        holder.call(second, step, 'read_delivery_discussion', {'after_reference': None, 'limit': 100})
        holder.call(second, step, 'post_delivery_message', {'text': 'Acknowledged.', 'reply_to': message['reference']})
        proof = self.assess(holder, activation)
        self.assertTrue(proof['component_gates']['native_reconstruction_valid'])
        self.assertEqual(proof['communication']['linked_reply_candidates'], [])

    def test_scheduled_partial_delivery_is_not_reported_as_unscheduled(self):
        _, holder, _ = self.new('acceptance')
        for actor in self.plan:
            self.build_file(holder, actor)
        self.send(holder)
        actor = next(iter(self.plan))
        state = holder.business_state(actor)
        self.assertTrue(state['delivery_current'])
        self.assertFalse(state['delivery_complete'])
        check = {'actor_complete': False, 'actor_business_state': state}
        self.assertIn('A current delivery is scheduled.', run.current_work_feedback(holder, actor, check))
        self.call(holder, actor, 'cancel_delivery_packet')
        self.assertFalse(holder.business_state(actor)['delivery_current'])

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
