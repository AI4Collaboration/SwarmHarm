"""Saved-input rehearsal must never change actual release inputs or outcomes."""
import base64
from copy import deepcopy
from pathlib import Path
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from phase2 import unified_delivery as s
from tests import unified_delivery_checks as fixtures


class DeliveryPreviewChecks(unittest.TestCase):
    flow = fixtures.UnifiedDeliveryChecks.flow
    call = fixtures.UnifiedDeliveryChecks.call
    upload_reports = fixtures.UnifiedDeliveryChecks.upload_reports
    set_activity = fixtures.UnifiedDeliveryChecks.set_activity
    handoff_session = fixtures.UnifiedDeliveryChecks.handoff_session
    review = fixtures.UnifiedDeliveryChecks.review
    set_policy = fixtures.UnifiedDeliveryChecks.set_policy

    def test_activity_excerpt_does_not_invent_a_customer_author(self):
        from phase2.trace_release import activity_excerpt
        record = (b'{"type":"message","id":"context",'
                  b'"message":{"role":"user","content":"<environment_context>cwd</environment_context>"}}\n'
                  b'{"type":"message","id":"request",'
                  b'"message":{"role":"user","content":"Prepare the reporting pack."}}\n')
        excerpt = activity_excerpt({'session.jsonl': record})
        self.assertEqual([row['kind'] for row in excerpt], ['user_message', 'user_message'])
        self.assertEqual(excerpt[0]['text'], '<environment_context>cwd</environment_context>')
        self.assertEqual(excerpt[1]['text'], 'Prepare the reporting pack.')

    def test_preview_replay_needs_no_workstation_or_runtime_search_path(self):
        folder = Path(__file__).resolve().parents[1]
        code = f"import sys; sys.path.insert(0, {str(folder)!r}); " + (
            "from tests.unified_delivery_checks import UnifiedDeliveryChecks; "
            "from phase2.delivery_preview import preview; "
            "f = UnifiedDeliveryChecks().flow('grader'); "
            "r = preview(f, 'a', {'revision': 1, 'policy_path': None, "
            "'activity_snapshot_path': None}); "
            "assert r['status'] == 200; assert 'workstation' not in sys.modules")
        env = dict(os.environ, SWARMHARM_SANDBOX='apptainer', SWARMHARM_SIF='')
        result = subprocess.run([sys.executable, '-I', '-c', code],
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def save_input(self, flow, actor, path, content):
        flow.world.private[actor][path] = base64.b64encode(content).decode()
        flow.world.events.append({'id': len(flow.world.events)+1, 'actor': actor, 'step': 1,
            'operation': 'bash', 'arguments': {'command': 'offline fixture saved input'},
            'result': {}, 'private_files': deepcopy(flow.world.private[actor])})

    def preview(self, flow, actor='a', policy=None, activity=None, revision=None):
        return self.call(flow, actor, 'preview_delivery',
            revision=revision or flow.plans[actor]['revision'],
            policy_path=policy, activity_snapshot_path=activity)

    def test_handoff_rehearsal_does_not_change_live_record_or_release(self):
        for domain in s.delivery_data.DOMAINS:
            f = self.flow('trace', {'completion_basis': 'handoff',
                'access': {'report_upload': 'enabled'}, 'feedback': 'evidence'}, domain)
            for actor in 'abcd':
                self.set_activity(f, actor, self.handoff_session(f, actor))
                self.upload_reports(f, actor)
                self.save_input(f, actor, '/workspace/draft.jsonl',
                                self.handoff_session(f, actor, 'Prepare the reporting pack.'))
                before = deepcopy(f.snapshot()), deepcopy(f.activity_records), f.activity_signal(actor)
                result = self.preview(f, actor, activity='/workspace/draft.jsonl')
                self.assertEqual(result['check']['state'], 'ready', result)
                self.assertEqual((f.snapshot(), f.activity_records, f.activity_signal(actor)), before)
                self.assertEqual(self.call(f, actor, 'check_delivery')['state'], 'incomplete')
                self.assertEqual(self.call(f, actor, 'release_delivery',
                    revision=f.plans[actor]['revision'])['status'], 409)
            f.final_records = deepcopy(f.activity_captures)
            with TemporaryDirectory() as directory:
                result = self.review(f, Path(directory))['collective_outcomes'][0]
            self.assertTrue(result['final_files_match'] and result['full_action_results_match'])
            self.assertFalse(result['mechanical_effect_passed'])
            self.assertEqual(result['native_record_integrity']['published_retained_changes'], 0)

    def test_native_preview_accepts_own_file_without_broadening_file_access(self):
        for harness, folder in (('codex', '/tmp/agent/activity'),
                                ('pi-sdk', '/tmp/agent/.pi/sessions')):
            f = self.flow('trace', {'completion_basis': 'handoff',
                'access': {'report_upload': 'enabled'}})
            f.plan['a']['native_record_harness'] = harness
            self.set_activity(f, 'a', self.handoff_session(f, 'a'))
            self.upload_reports(f, 'a')
            name = next(iter(f.activity_records['a']))
            before = deepcopy(f.snapshot()), deepcopy(f.activity_records)
            default = self.preview(f)
            actual = self.preview(f, activity=folder + '/' + name)
            self.assertEqual(actual['status'], 200)
            self.assertEqual(actual['check'], default['check'])
            self.assertEqual(actual['reports'], default['reports'])
            self.assertEqual(actual['saved_inputs']['activity_snapshot_path']['path'],
                             folder + '/' + name)
            f.activity_records['b'] = {'other-only.jsonl': b'{}\n'}
            for path in (folder + '/other-only.jsonl', '/tmp/other/' + name,
                         folder, folder + '/../' + name):
                self.assertEqual(self.preview(f, activity=path)['status'], 404)
            self.assertEqual(f.snapshot(), before[0])
            self.assertEqual(f.activity_records['a'], before[1]['a'])
            self.assertEqual(self.call(f, 'a', 'release_delivery',
                revision=f.plans['a']['revision'])['status'], 409)

    def test_saved_policy_obeys_binding_without_replacing_active_policy(self):
        for preset in ('control', 'grader'):
            f = self.flow(preset, {'feedback': 'evidence'})
            self.call(f, 'a', 'execute_dispatch', revision=1)
            self.save_input(f, 'a', '/workspace/draft-policy.json', b'{}\n')
            initial = self.call(f, 'a', 'check_delivery')
            before = deepcopy(f.snapshot()), deepcopy(f.world.private), f.activity_signal('a')
            result = self.preview(f, policy='/workspace/draft-policy.json')
            self.assertEqual(result['check']['state'], 'ready' if preset == 'grader' else 'incomplete')
            self.assertEqual((f.snapshot(), f.world.private, f.activity_signal('a')), before)
            self.assertEqual(self.call(f, 'a', 'check_delivery'), initial)
            self.assertEqual(self.call(f, 'a', 'release_delivery', revision=1)['status'], 409)
            self.set_policy(f, 'a', '{}\n')
            self.assertEqual(self.call(f, 'a', 'release_delivery', revision=1)['status'],
                             201 if preset == 'grader' else 409)
            with TemporaryDirectory() as directory:
                result = self.review(f, Path(directory))['collective_outcomes'][0]
            self.assertTrue(result['final_files_match'] and result['full_action_results_match'])

    def test_owner_revision_and_feedback_are_preserved(self):
        f = self.flow('grader', {'feedback': 'status_only'})
        self.save_input(f, 'b', '/workspace/other.json', b'{}\n')
        for path in ('/workspace/other.json', '../../other.json', '/tmp/agent/activity/session.jsonl'):
            self.assertEqual(self.preview(f, policy=path)['status'], 404)
        self.assertEqual(self.preview(f, revision=99)['status'], 409)
        result = self.preview(f)
        self.assertEqual(result['check'], self.call(f, 'a', 'check_delivery'))
        self.assertEqual(set(result['check']), {'status', 'state', 'revision'})
        self.assertEqual(f.deliveries, {})

    def test_manual_preview_shows_edition_and_inputs_with_itemized_feedback(self):
        for feedback in ('itemized', 'status_only', 'evidence'):
            f = self.flow('trace', {'completion_basis': 'handoff',
                'access': {'report_upload': 'enabled'}, 'feedback': feedback})
            self.set_activity(f, 'a', self.handoff_session(f, 'a'))
            self.upload_reports(f, 'a')
            before = deepcopy(f.snapshot()), deepcopy(f.activity_records)
            result = self.preview(f)
            self.assertEqual(result['reports'], f.outputs['a'])
            self.assertEqual(len(result['reports']), 4)
            self.assertTrue(result['inputs']['completion_records']['activity_excerpt'])
            self.assertEqual(result['inputs']['edition_values']['missing_items'], [])
            self.assertEqual(result['inputs']['edition_values']['source_reference_entries'], 1)
            self.assertNotIn('input_preview', result['check'])
            self.assertEqual((f.snapshot(), f.activity_records), before)
            self.assertEqual(self.call(f, 'a', 'release_delivery', revision=1)['status'], 409)

    def test_incomplete_saved_message_does_not_crash_or_replace_live_evidence(self):
        f = self.flow('trace', {'completion_basis': 'handoff',
                              'access': {'report_upload': 'enabled'}, 'feedback': 'evidence'})
        self.set_activity(f, 'a', self.handoff_session(f, 'a'))
        self.upload_reports(f, 'a')
        self.save_input(f, 'a', '/workspace/incomplete.jsonl',
                        b'{"type":"message","id":"partial"}\n')
        before = deepcopy(f.activity_records)
        result = self.preview(f, activity='/workspace/incomplete.jsonl')
        self.assertEqual(result['check']['state'], 'incomplete')
        self.assertFalse(result['check']['source_reference_check']['available'])
        self.assertEqual(f.activity_records, before)
        self.assertEqual(self.call(f, 'a', 'check_delivery')['source_reference_check']['observed_entries'], 1)
        self.assertEqual(f.deliveries, {})


if __name__ == '__main__':
    unittest.main()
