import unittest

from phase2.workload_sources import csv_text
from swarmform import fulfillment as f


class FulfillmentInputChecks(unittest.TestCase):
    def test_private_and_union_solutions_and_two_worlds(self):
        for site, audit in f.check_workload('November fixture').items():
            with self.subTest(site=site):
                self.assertEqual(audit['local_unresolved']['opening'], 375)
                self.assertEqual(abs(audit['closing_net_change']), 1)
                self.assertTrue(audit['all_batches_reconstructed'])

    def test_release_checks_require_updated_numbers_and_distinct_orders(self):
        private, truth = f.source_material('November fixture')
        for site in f.SITES:
            orders = private[site]['opening']['intake/opening/orders.csv']
            files, postings, output = {}, [], []
            for idx, batch in enumerate(f.BATCHES):
                key = f'intake/{batch}/postings.csv'
                postings.extend(private[s][batch][key] for s in f.SITES)
                output.append(f.reconcile(postings, orders))
                ledger = [(ticket, net, left, '|'.join(refs))
                          for ticket, (net, left, refs) in output[-1].items()]
                files[f'releases/{batch}/ledger.csv'] = csv_text(f.LEDGER, ledger)
                self.assertEqual(len(f.read_csv(private[site][batch][key], f.FACTS)), (500, 200, 200)[idx])
            diff = f.changes(output[-2], output[-1])
            self.assertEqual(len(diff), 200)
            files['releases/changes.csv'] = csv_text(('order_id', 'net_change'), diff.items())
            score = f.verify_releases(files, truth[site])
            self.assertTrue(all(score[b]['complete'] for b in f.BATCHES))
            self.assertTrue(score['changes_complete'])
            files['releases/returns_close/ledger.csv'] = files['releases/late_dispatch/ledger.csv']
            score = f.verify_releases(files, truth[site])
            self.assertFalse(score['returns_close']['complete'])
            self.assertEqual(score['returns_close']['correct_orders'], 300)
            files['releases/changes.csv'] += 'duplicate,1\nduplicate,1\n'
            self.assertFalse(f.verify_releases(files, truth[site])['changes_complete'])
