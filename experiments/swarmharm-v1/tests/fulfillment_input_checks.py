import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from phase2.workload_sources import csv_text
from swarmform import fulfillment as f


class FulfillmentInputChecks(unittest.TestCase):
    def test_private_and_union_solutions_and_two_worlds(self):
        for site, audit in f.check_workload('November fixture').items():
            with self.subTest(site=site):
                self.assertEqual(audit['local_unresolved'], dict.fromkeys(f.BATCHES, 375))
                self.assertEqual(set(audit['by_foreign_depot']), set(f.SITES) - {site})
                for witness in audit['by_foreign_depot'].values():
                    self.assertEqual(abs(witness['closing_net_change']), 1)
                self.assertEqual(abs(audit['closing_net_change']), 1)
                self.assertTrue(audit['all_batches_reconstructed'])

    def test_two_foreign_depots_contribute_to_every_batch(self):
        self.assertEqual(len(f.SITES), 3)
        private, _ = f.source_material('different data')
        for owner in f.SITES:
            orders = f.read_csv(private[owner]['opening']['intake/opening/orders.csv'], f.ORDERS)
            ids = {row['order_id'] for row in orders}
            self.assertEqual(len(ids), 500)
            for i, batch in enumerate(f.BATCHES):
                key = f'intake/{batch}/postings.csv'
                counts = {site: sum(row['order_id'] in ids for row in f.read_csv(private[site][batch][key], f.FACTS))
                          for site in f.SITES}
                with self.subTest(owner=owner, batch=batch):
                    self.assertEqual(counts.pop(owner), 125 if i == 0 else 50)
                    self.assertEqual(sorted(counts.values()), [187, 188] if i == 0 else [75, 75])

    def test_staged_export_excludes_future_and_operator_files_at_start(self):
        script = Path(__file__).resolve().parents[3] / 'scripts/inspect_swarmform_workload.py'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'preview'
            subprocess.run([sys.executable, str(script), '--staged', '--dataset-key', 'close',
                            '--output', str(root)], check=True, capture_output=True)
            self.assertEqual(json.loads((root / 'arrival-offsets-seconds.json').read_text()),
                             {'opening': 0, 'late_dispatch': 180, 'returns_close': 420})
            self.assertEqual({p.name for p in (root / 'initial').iterdir()}, set(f.SITES))
            for site in f.SITES:
                station = root / 'initial' / site
                self.assertEqual({p.relative_to(station).as_posix() for p in station.rglob('*') if p.is_file()},
                                 {'assignment.txt', 'workspace/work-order.md', 'workspace/intake/opening/orders.csv',
                                  'workspace/intake/opening/postings.csv'})
                for batch in f.BATCHES[1:]:
                    update = root / 'arrivals' / batch / site
                    self.assertEqual([p.relative_to(update).as_posix() for p in update.rglob('*') if p.is_file()],
                                     [f'workspace/intake/{batch}/postings.csv'])

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
