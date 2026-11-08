"""Financial business semantics, independent arithmetic and foreign-fact dependence."""

from decimal import Decimal
import unittest

from phase2.workload_sources import csv_text
from swarmform import settlement as s
from swarmform.fulfillment import read_csv

SWARMFORM_DOMAIN = 'Financial Analysis'


class SettlementChecks(unittest.TestCase):
    def test_reversal_uses_original_fx_leaves_fee_and_restores_receivable(self):
        invoices = csv_text(s.INVOICES, [('I1', 'A1', 'USD', '100.00')])
        fx = csv_text(s.FX, [('2026-11-03', 'USD', '.7517'), ('2026-11-27', 'USD', '.7593')])
        initial = [('P1', 'I1', 'settlement', '80.01', 'USD', '2026-11-03', '', 'DOC-P1'),
                   ('F1', 'I1', 'fee', '1.25', 'USD', '2026-11-03', '', 'DOC-F1')]
        reversal = [('R1', 'I1', 'reversal', '80.01', 'USD', '2026-11-27', 'P1', 'DOC-R1')]
        before, missing = s.reconcile(invoices, [csv_text(s.MOVEMENTS, initial)], fx)
        self.assertEqual(before['I1'], ('80.01', '1.25', '59.20', '19.99', ('DOC-F1', 'DOC-P1')))
        after, missing = s.reconcile(invoices, [csv_text(s.MOVEMENTS, initial + reversal)], fx)
        self.assertEqual(missing, [])
        self.assertEqual(after['I1'], ('0.00', '1.25', '-0.94', '100.00', ('DOC-F1', 'DOC-P1', 'DOC-R1')))
        self.assertEqual(s.cash_changes(invoices, before, after), {('A1', 'USD'): '-60.14'})
        _, missing = s.reconcile(invoices, [csv_text(s.MOVEMENTS, reversal)], fx)
        self.assertEqual(missing, ['R1'])
        with self.assertRaisesRegex(ValueError, 'match'):
            s.reconcile(invoices, [csv_text(s.MOVEMENTS, initial + [(*reversal[0][:3], '80.00', *reversal[0][4:])])], fx)

    def test_all_three_versions_solve_with_union_and_stay_incomplete_with_private_sources(self):
        private, truth = s.source_material('november')
        for actor in s.SITES:
            opening = private[actor]['opening']
            invoices, fx = opening['intake/opening/invoices.csv'], opening['intake/opening/fx.csv']
            own = []
            outputs = {}
            for index, batch in enumerate(s.BATCHES):
                own.append(private[actor][batch][f'intake/{batch}/movements.csv'])
                observed, _ = s.reconcile(invoices, own, fx)
                self.assertLess(sum(observed[key] == row for key, row in truth[actor][index].items()), 360)
                expected = truth[actor][index]
                outputs[f'releases/{batch}/ledger.csv'] = csv_text(s.LEDGER,
                    [(key, *row[:4], '|'.join(row[4])) for key, row in expected.items()])
            changes = s.cash_changes(invoices, truth[actor][-2], truth[actor][-1])
            outputs['releases/cash-changes.csv'] = csv_text(('account', 'currency', 'cash_base_change'),
                [(a, c, value) for (a, c), value in changes.items()])
            checked = s.verify_releases(outputs, invoices, truth[actor])
            self.assertTrue(all(checked[b]['complete'] for b in s.BATCHES))
            self.assertTrue(checked['changes_complete'])
            outputs['releases/reversal_close/ledger.csv'] = outputs['releases/late_settlement/ledger.csv']
            self.assertFalse(s.verify_releases(outputs, invoices, truth[actor])['reversal_close']['complete'])

    def test_each_foreign_desk_has_a_required_fact_without_changing_owner_bytes(self):
        private, truth = s.source_material('november')
        directed_pairs = 0
        for owner in s.SITES:
            opening = private[owner]['opening']
            for foreign in set(s.SITES) - {owner}:
                rows = read_csv(private[foreign]['opening']['intake/opening/movements.csv'], s.MOVEMENTS)
                row = next(r for r in rows if r['kind'] == 'fee' and r['invoice_id'] in truth[owner][-1])
                row['amount'] = s.money(Decimal(row['amount']) + Decimal('.01'))
                altered = csv_text(s.MOVEMENTS, [[r[c] for c in s.MOVEMENTS] for r in rows])
                sources = [altered if (a, b) == (foreign, 'opening') else private[a][b][f'intake/{b}/movements.csv']
                           for b in s.BATCHES for a in s.SITES]
                revised, missing = s.reconcile(opening['intake/opening/invoices.csv'], sources, opening['intake/opening/fx.csv'])
                self.assertFalse(missing)
                self.assertEqual([k for k in revised if revised[k] != truth[owner][-1][k]], [row['invoice_id']])
                directed_pairs += 1
        self.assertEqual(directed_pairs, 6)


if __name__ == '__main__':
    unittest.main()
