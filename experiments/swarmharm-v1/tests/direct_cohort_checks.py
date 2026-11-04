"""Completion receipts bind direct responses without provider timestamps."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from phase1 import carrier_resource_review, carrier_trace_review


class DirectCohortChecks(TestCase):
    def result(self, *, kind='direct-api', receipt=12, completed=None, duplicate=False):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'natural').mkdir()
            for name in ('activation.json', 'actors.json'):
                (root/'natural'/name).touch()
            stamp = lambda n: f'1970-01-01T00:00:{n:02d}+00:00'
            activation = {'actors':['a'], 'policy':'simultaneous_start_barrier', 'ordered_arrivals':False,
                'all_workstations_ready_before_release':True, 'all_agent_sessions_ready_before_release':True,
                'workstation_count':1, 'activated_at':stamp(10)}
            rows = [] if receipt is None else [
                {'path':'natural/a/trace/0001', 'status':'completed', 'at':stamp(receipt)}]
            if duplicate:
                rows *= 2
            data = {'activation.json':activation,
                'actors.json':{'a':{'started_at':stamp(10), 'finished_at':stamp(20)}},
                '0001.response.json':{'status':'completed', 'completed_at':completed},
                'transport-attempts.json':rows}
            reg = {'plan':{'natural':{'a':{}}}, 'harness':{'kind':kind},
                'budget':{'active_contexts_natural':1},
                'connected_protocol':{'overlapping_execution':True, 'simultaneous_start_barrier':True,
                    'ordered_arrivals':False, 'all_subjects_active_until_global_terminal':True}}
            anchor = {'path':'natural/a/trace/0001.response.json'}
            signal = {'write_event':1, 'read_event':1, 'producer_anchor':anchor, 'consumer_anchor':anchor}
            def read(root, path, sealed):
                self.assertTrue(sealed)
                return data[path.name], {'path':path.name, 'sha256':'fixture'}
            with patch.object(carrier_trace_review, 'read_file', side_effect=read):
                return carrier_resource_review.cohort(root, reg, [{'id':1, 'at':stamp(13)}], [signal])

    def test_sealed_local_receipt_establishes_overlap(self):
        self.assertTrue(self.result()['passed'])
        self.assertFalse(self.result(receipt=21)['passed'])

    def test_missing_or_ambiguous_receipt_cannot_pass(self):
        for kw in ({'receipt':None}, {'duplicate':True}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.result(**kw)

    def test_legacy_timestamp_path_is_unchanged(self):
        self.assertTrue(self.result(kind='pi', completed=12)['passed'])
        self.assertFalse(self.result(kind='pi', completed=None)['passed'])
        self.assertFalse(self.result(completed=21)['passed'])

    def test_codex_response_groups_use_sealed_local_completion(self):
        result = self.result(kind='codex')
        self.assertTrue(result['passed'])
        self.assertIn('native_completion_receipts', result)
        self.assertFalse(self.result(kind='codex', receipt=21)['passed'])
        for kw in ({'receipt':None}, {'duplicate':True}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.result(kind='codex', **kw)
