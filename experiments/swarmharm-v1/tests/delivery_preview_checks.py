"""Saved-input rehearsal must never change actual release inputs or outcomes."""
import base64
from copy import deepcopy
from pathlib import Path
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
