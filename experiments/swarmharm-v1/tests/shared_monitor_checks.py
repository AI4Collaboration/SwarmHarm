"""All current business surfaces have attributed observations, not inferred intent."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

import domain_runtime
import run
from phase1 import lab, shared_files, shared_monitor, carrier_registration, engagement_controls
from tests.shared_file_checks import plan_for


class SharedMonitorChecks(unittest.TestCase):
    def world(self, scenario):
        world = lab.World(plan_for(scenario))
        world.private = {actor: lab.files(item, actor) for actor, item in world.plan.items()}
        self.addCleanup(world.close)
        return world

    def call(self, world, actor, operation, arguments=None):
        return world.call(actor, len(world.events) + 1, operation, arguments or {})

    def submission(self, world, actor):
        scenario = world.plan[actor]['scenario']
        mechanics = domain_runtime.mechanics(scenario)
        rows = [row for owner in world.plan for row in world.service(owner).batch['reviews']]
        check, other = rows[:2]
        batch = world.service(actor).batch
        if scenario == 'engineering-capacity':
            from scenarios import engineering
            other = engineering.dependency_for(check, rows)
            args = {'check_id': check['check_id'], 'source_record_id': check['record_id'],
                    'attestation_reference': check['attestation_reference'],
                    'runtime_units': check['runtime_units'], 'release_status': 'ready',
                    'dependency_source_record_id': other['record_id'],
                    'dependency_attestation_reference': other['attestation_reference']}
        else:
            args = engagement_controls.arguments(scenario, check['check_id'],
                mechanics.archive_record(batch, check['record_id']),
                mechanics.archive_record(batch, other['record_id']))
        for record_id in (check['record_id'], other['record_id']):
            self.assertEqual(self.call(world, actor, 'fetch_archive', {'record_id': record_id})['status'], 200)
        self.assertEqual(self.call(world, actor, 'submit_review', args)['status'], 202)
        return args

    def test_all_four_configurations_monitor_shared_filing_without_changing_inputs(self):
        for scenario in domain_runtime.SUPPORTED:
            w = self.world(scenario); a, b, *_ = w.plan
            descriptor = carrier_registration.descriptor(w.plan)
            self.assertEqual(descriptor['shared_environment_monitor'], shared_monitor.inventory(w.plan))
            self.submission(w, a)
            source = w.events[-1]['id']
            self.call(w, b, 'filing_status')
            audit = shared_monitor.filing_replay(w.plan, w.events)
            self.assertEqual([(row['source_event'], row['read_event'], row['feature'])
                for row in audit['foreign_observations']], [(source, w.events[-1]['id'], 'filing_receipt')])
            self.assertEqual(audit['samples'][-1]['source_events'], [source])
            original = deepcopy(w.events)
            original[-1]['result']['filing']['submissions'][0]['recorded_by'] = b
            with self.assertRaisesRegex(ValueError, 'filing status'):
                shared_monitor.filing_replay(w.plan, original)
            legacy = deepcopy(w.plan)
            for item in legacy.values(): item.pop(shared_files.FIELD)
            self.assertIsNone(shared_monitor.inventory(legacy))
            self.assertEqual(shared_monitor.filing_replay(legacy, w.events)['foreign_observations'], [])
            self.assertEqual(lab.tools(w.plan[a]), lab.tools(legacy[a]))
            self.assertEqual(lab.task(w.plan[a]), lab.task(legacy[a]))

    def test_rejected_missing_source_is_not_an_already_filed_signal(self):
        w = self.world('engineering-capacity'); a, b, *_ = w.plan
        args = self.submission(w, a)
        self.assertEqual(self.call(w, b, 'submit_review', args)['status'], 409)
        audit = shared_monitor.filing_replay(w.plan, w.events)
        self.assertEqual(audit['foreign_observations'], [])
        for key in ('source_record_id', 'dependency_source_record_id'):
            self.call(w, b, 'fetch_archive', {'record_id': args[key]})
        self.call(w, b, 'submit_review', args)
        self.assertEqual(shared_monitor.filing_replay(w.plan, w.events)['foreign_observations'][-1]['feature'],
                         'filing_already_filed')

    def test_source_revision_preserves_original_receipt_author_and_version(self):
        w = self.world('engineering-capacity'); a, b, *_ = w.plan
        self.submission(w, a); source = w.events[-1]['id']
        w.publish_final_build()
        self.call(w, b, 'filing_status')
        audit = shared_monitor.filing_replay(w.plan, w.events)
        self.assertEqual(audit['foreign_observations'][-1]['source_event'], source)
        self.assertEqual(audit['foreign_observations'][-1]['author'], a)

    def test_notice_binds_all_causes_without_selecting_one_sender(self):
        world = SimpleNamespace(plan=plan_for(), events=[
            {'id': 1, 'actor': 'job-0', 'shared_changes': [{'path': '/one', 'sha256': 'one'}]},
            {'id': 2, 'actor': 'job-1', 'shared_changes': [{'path': '/two', 'sha256': 'two'}]}])
        before = {'case_revisions': {}, 'case_entries': {}}
        after = {'case_revisions': {'case': 'revision'}, 'case_entries': {'case': [
            {'path': '/one', 'sha256': 'one', 'event': 'note_added'},
            {'path': '/two', 'sha256': 'two', 'event': 'note_added'}]}}
        message = run.activity_feedback(after, before)
        # The sidecar adds attribution without being appended to the visible notification.
        bound = run.monitored_notice(world, after, before)['shared_monitor']
        self.assertEqual([row['event'] for row in bound['source_records']], [1, 2])
        self.assertNotIn('job-', run.activity_feedback(after, before))
        self.assertNotIn('source_records', message)
        damaged = deepcopy(after); damaged['case_entries']['case'][0]['sha256'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'no recorded source'):
            run.monitored_notice(world, damaged, before)

    def test_collector_preserves_sources_when_notice_has_no_descriptive_entries(self):
        world = SimpleNamespace(plan=plan_for(), events=[
            {'id': 1, 'actor': 'job-0', 'shared_changes': [{'path': '/one', 'sha256': 'one'}]}])
        filing = {'revision': 'updated', 'relevant_cross_job_records': 1,
                  'case_revisions': {'case': 'changed'},
                  'monitored_case_entries': {'case': [{'path': '/one', 'sha256': 'one'}]}}
        previous = {'revision': 'initial', 'relevant_cross_job_records': 0,
                    'case_revisions': {}, 'monitored_case_entries': {}}
        idle = {'revision': None, 'relevant_cross_job_records': 0}
        before = run.combined_activity_signal(previous, idle, False)
        after = run.combined_activity_signal(filing, idle, False)
        self.assertNotIn('case_entries', after)
        bound = run.monitored_notice(world, after, before)['shared_monitor']
        self.assertEqual(bound['source_records'], [
            {'event': 1, 'author': 'job-0', 'path': '/one', 'sha256': 'one'}])
        legacy = deepcopy(filing); legacy.pop('monitored_case_entries')
        old_after = run.combined_activity_signal(legacy, idle, False)
        self.assertEqual({k:v for k,v in after.items() if k != 'monitored_case_entries'}, old_after)
        extension = SimpleNamespace(activated=False)
        args = dict(extension=extension, actor='job-1', check={'complete': False}, delivered=before,
                    cue_condition='agent_initiated_activity')
        self.assertEqual(run.work_notice(signal=after, **args), run.work_notice(signal=old_after, **args))
        self.assertEqual(run.work_notice(signal=after, **{**args, 'delivered': after}), (None, None))
        # Observer metadata must neither expose identities nor select another notice kind.
        self.assertEqual(run.activity_feedback(after, before), 'New activity entries for case.')
        filing['monitored_case_entries']['case'].clear()
        self.assertEqual(len(after['monitored_case_entries']['case']), 1)

    def test_collector_selects_only_the_active_workflow_sources(self):
        filing = {'revision': 'filing', 'relevant_cross_job_records': 1,
                  'case_revisions': {'old': 'old'}, 'monitored_case_entries': {'old': []}}
        continuation = {'revision': 'delivery', 'relevant_cross_job_records': 1,
                        'case_revisions': {'new': 'new'},
                        'monitored_case_entries': {'new': [{'path': '/new', 'sha256': 'new'}]}}
        after = run.combined_activity_signal(filing, continuation, True)
        self.assertEqual(after['case_revisions'], {'new': 'new'})
        self.assertEqual(after['monitored_case_entries'], continuation['monitored_case_entries'])
