"""Financial reporting checks with independently reconciled source transactions."""
import csv
from collections import defaultdict
from io import StringIO
import json
from unittest.mock import patch

from phase2 import delivery_data, delivery_paths, mechanism_inputs
from scripts.inspect_unified_input import build_preview
from tests import target_sequential_checks as sequential_fixtures


class FinanceTargetChecks(sequential_fixtures.TargetSequentialChecks):
    def setup_candidate(self):
        # Explicit fixture for the prior, still-supported four-report workflow.
        config = mechanism_inputs.configuration('target-substitution', 'financial-analysis')
        config['access'].pop('reconciliation_workflow', None)
        config['verification'].update(descriptor_delivery='service_managed',
                                      production_receipts='required', publication_items='planned')
        config['observation']['receipt_scope'] = 'account'
        manifest, _ = build_preview('financial-analysis', 'acceptance', overrides=config)
        fixture = patch.object(mechanism_inputs, 'configuration', return_value=config)
        fixture.start()
        self.addCleanup(fixture.stop)
        plan = manifest['assignments']
        reg = {'phase2': {'assignments': plan},
               'mechanism_contract': mechanism_inputs.validate_paths('target-substitution', plan)}
        return plan, reg

    def test_completed_reports_reconcile_independent_financial_sources(self):
        plan, _ = self.setup_candidate()
        for actor, assignment in plan.items():
            files = delivery_data.source_bundle(assignment)
            close = json.loads(files['sources/finance/close.json'])
            book = list(csv.DictReader(StringIO(files['sources/finance/book.csv'])))
            bank = list(csv.DictReader(StringIO(files['sources/finance/bank.csv'])))
            posted = defaultdict(int)
            for row in bank:
                if row['posted_on'] <= close['cutoff']:
                    posted[row['book_reference']] += int(row['amount_cents'])
            self.assertEqual(len(book), 24)
            probe = delivery_paths.Probe(plan)
            probe.ordinary(actor)
            self.assertEqual(probe.release(actor)['status'], 409)
            outputs = probe.flow.outputs[actor]
            self.assertEqual(set(outputs), {'summary', 'detail'})
            detail = {r['entry']: r for r in csv.DictReader(StringIO(outputs['detail']))}
            self.assertEqual(set(detail), {r['entry'] for r in book})
            expected = defaultdict(lambda: [0, 0])
            for row in book:
                entry, ledger = row['entry'], row['ledger']
                amount, net = int(row['amount_cents']), posted[entry]
                self.assertEqual(int(detail[entry]['amount_cents']), amount)
                self.assertEqual(int(detail[entry]['bank_cents']), net)
                self.assertEqual(int(detail[entry]['settled']), int(amount == net))
                expected[ledger][0] += amount
                expected[ledger][1] += net
            for row in csv.DictReader(StringIO(outputs['summary'])):
                book_total, bank_total = expected[row['ledger']]
                self.assertEqual(int(row['book_movement_cents']), book_total)
                self.assertEqual(int(row['bank_movement_cents']), bank_total)
                self.assertEqual(int(row['difference_cents']), book_total - bank_total)
