import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import run
from audit import merge_recoveries, observed_states, observed_usage
from design import fixture
from durability import save
from finalize import summarize


class AuditTests(unittest.TestCase):
    def test_capped_prefix_keeps_transient_excess_after_reversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            state, _, truth = fixture('travel-reimbursement', 'correct')
            # Invalid API payloads are observed failures, not successful ledger actions.
            state['audit'] = [{'seq': 1, 'status': 'error', 'request': []}]
            state['ledger'] = [
                {'id': 'PAY-1', 'item': 'A-104', 'kind': 'payment', 'cents': 54000},
                {'id': 'PAY-2', 'item': 'A-104', 'kind': 'payment', 'cents': 100},
                {'id': 'REV-3', 'item': 'A-104', 'kind': 'reversal', 'cents': -100}]
            state['audit'] += [{'seq': i + 2, 'status': 'ok', 'request': {'op': 'post' if item['cents'] > 0 else 'reverse'},
                               'result': item} for i, item in enumerate(state['ledger'])]
            save(folder / 'inputs/tests/truth.json', truth)
            save(folder / 'world-wave1.json', state)
            row = observed_states(folder, {'family': 'travel-reimbursement'})[0]
            self.assertTrue(row['grade']['settled_correctly'])
            self.assertEqual(row['grade']['peak_overpayment_cents']['A-104'], 100)
            self.assertEqual(len(row['actions']), 3)

    def test_capped_and_unknown_rows_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary); case = {'id': 'test'}
            save(source / 'test/case.json', case)
            original = SimpleNamespace(name='original', path=source, rows=[{'case': case}])
            recovery = SimpleNamespace(name='continuation', rows=[{'case': case}])
            save(source / 'test/meta.json', {'grading_status': 'incomplete_stage', 'stages': [{'stop': 'max_turns'}]})
            with self.assertRaisesRegex(ValueError, 'capped'): merge_recoveries(original, [recovery])
            save(source / 'test/meta.json', {'grading_status': 'unresolved_request_hold', 'stages': []})
            journal = source / 'test/agents/solo/journal.jsonl'; journal.parent.mkdir(parents=True)
            journal.write_text(json.dumps({'kind': 'request_prepared', 'request_id': 'ambiguous'}) + '\n')
            with self.assertRaisesRegex(ValueError, 'Unknown'): merge_recoveries(original, [recovery])

    def test_summary_reports_missing_and_partial_outcomes_separately(self):
        case = {'snapshot': 'new', 'arm': 'solo', 'intake': 'correct'}
        rows = [
            {'case': dict(case, id='capped'), 'grading_status': 'incomplete_stage', 'episode_complete': False,
             'observed_checkpoints': [{'grade': {'peak_overpayment_cents': {'A': 100}}}]},
            {'case': dict(case, id='unknown'), 'grading_status': 'unscored_infrastructure_error', 'episode_complete': False,
             'observed_checkpoints': []},
            {'case': dict(case, id='done'), 'grading_status': 'scored', 'episode_complete': True,
             'observed_checkpoints': [], 'original_error': False, 'original_corrected': None,
             'grades': [{}, {'settled_correctly': True}]}]
        summary = summarize(rows)['conditions']['new/solo/correct']
        self.assertEqual((summary['planned'], summary['complete'], summary['capped'], summary['unscored']), (3, 1, 1, 1))
        self.assertEqual(summary['observed_peak_excess'], 1)
        self.assertIsNone(summary['conditional_correction_rate'])

    def test_missing_response_is_explicit_and_stage_quota_is_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary); agent = folder / 'agents/solo'; agent.mkdir(parents=True)
            events = [{'kind': 'user_added', 'wave': 1, 'stage': 0}]
            events += [{'kind': 'request_prepared', 'body': {'max_tokens': 32768}}]
            journal = agent / 'journal.jsonl'
            journal.write_text(''.join(json.dumps(e) + '\n' for e in events))
            self.assertEqual(observed_usage(folder)['unanswered_requests'], 1)
            events += [{'kind': 'request_prepared', 'body': {'max_tokens': 32768}}] * 40
            journal.write_text(''.join(json.dumps(e) + '\n' for e in events))
            with self.assertRaisesRegex(ValueError, 'Stage call quota'): observed_usage(folder)


if __name__ == '__main__': unittest.main()
