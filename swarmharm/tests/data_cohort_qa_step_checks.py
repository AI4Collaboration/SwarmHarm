"""Bind controller steps to collector turn filenames, not ATIF steps."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2.data_cohort_qa_bridge import CohortAdapter
from phase2.data_cohort_qa_candidate import ACCOUNTS
from phase2.data_cohort_qa_review import native_tool_bindings


class CohortStepChecks(unittest.TestCase):
    def test_native_turn_binds_both_controller_logs_including_multiple_tools(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            accounts = dict(zip(('a', 'b', 'c', 'd'), ACCOUNTS))
            adapter = CohortAdapter(root / 'natural/operator/data-cohort-qa-service', accounts, enforce_role=False)
            adapter.call('a', 7, 'list_catalog', {})
            adapter.call('a', 7, 'read_dataset', {'dataset': 'report-layouts'})
            world = {'events': [{'id': n, 'actor': 'a', 'step': 7, 'adapter_event_id': n, 'result': {}} for n in (1, 2)]}
            reg = {'phase2': {'assignments': {actor: {'account': account} for actor, account in accounts.items()}}}
            bindings = {n: {'event': n, 'tool_record': f'natural/a/trace/0007-tool-{n}.json', 'atif_step': 99+n} for n in (1, 2)}
            with patch('phase2.data_cohort_qa_review.bind_native', return_value=bindings):
                self.assertEqual(len(native_tool_bindings(root, reg, world)), 2)
                path = adapter.root / 'actor-events.jsonl'
                events = [json.loads(line) for line in path.read_text().splitlines()]
                for event in events:
                    event['step'] = 8
                path.write_text(''.join(json.dumps(event) + '\n' for event in events))
                for event in world['events']:
                    event['step'] = 8
                with self.assertRaisesRegex(ValueError, 'differs from native turn'):
                    native_tool_bindings(root, reg, world)


if __name__ == '__main__':
    unittest.main()
