"""Independent Phase 2 must not manufacture formation or source provenance."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import lab
import phase2_component as component
import run
import schedule
import review
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
            self.assertIsNone(reg['source_publication'])
            component.validate_sources(reg['plan']['natural'], reg['component_initial_state'])
            self.assertEqual(reg['input_hashes']['initial-file-audit.json'], run.sha(root/'initial-file-audit.json'))
            for initial in run.load(root/'initial-input-audit.json')['natural'].values():
                self.assertIn('publish_briefing', {t['name'] for t in initial['tools']})
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
