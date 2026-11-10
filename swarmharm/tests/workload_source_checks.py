"""Business-source transformations, produced bytes and independent accounting."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from phase2 import delivery_data as data, unified_delivery as scenario, workload_sources as work


class WorkloadSourceChecks(unittest.TestCase):
    def assignment(self, domain):
        return scenario.plan_for('abcd', domain=domain)['a']

    def test_all_domains_derive_original_outputs_from_distinct_sources(self):
        for domain in data.DOMAINS:
            for assignment in scenario.plan_for('abcd', domain=domain).values():
                with self.subTest(domain=domain, account=assignment['account']):
                    self.assertEqual(data.source_data(assignment), data.reference_data(assignment))
                    for item in data.ITEMS:
                        self.assertTrue(data.valid_report(assignment, item, data.render(assignment, item)))
                    files = data.source_bundle(assignment)
                    manifest = data.source_manifest(assignment)
                    self.assertEqual(set(manifest['inputs']), set(files))
                    for path, content in files.items():
                        self.assertEqual(manifest['source_sha256'][path], sha256(content.encode()).hexdigest())

    def test_reference_accounting_does_not_call_service_reducer(self):
        assignment = self.assignment('data-analysis')
        report = data.render(assignment, 'summary')
        with patch.object(work, 'reduce_sources', side_effect=AssertionError('shared implementation')):
            self.assertTrue(data.valid_report(assignment, 'summary', report))

    def test_cached_source_bytes_return_independent_mappings(self):
        assignment = self.assignment('knowledge-work')
        first = data.source_bundle(assignment)
        second = data.source_bundle(assignment)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        removed = next(iter(first))
        first.pop(removed)
        self.assertIn(removed, data.source_bundle(assignment))

    def test_engineering_runs_real_candidates_and_writes_verified_artifacts(self):
        assignment = self.assignment('engineering-capacity')
        files = data.source_bundle(assignment)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for path, content in files.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            folder = root / 'sources/engineering'
            subprocess.run([sys.executable, str(folder / 'run-build.py')], check=True,
                           capture_output=True, timeout=15)
            actual = json.loads((folder / 'build-results.json').read_text())
            truth = {r[0]: r for r in data.reference_data(assignment)['rows']}
            for result in actual:
                row = truth[result['run']]
                self.assertEqual((result['tests'], result['failed']), (row[2], row[3]))
                self.assertEqual('artifact' in result, bool(row[5]))
                if row[5]:
                    self.assertEqual(result['sha256'], sha256((folder / result['artifact']).read_bytes()).hexdigest())
            (folder / 'current.py').write_text((folder / 'previous.py').read_text())
            subprocess.run([sys.executable, str(folder / 'run-build.py')], check=True,
                           capture_output=True, timeout=15)
            self.assertEqual(list((folder / 'builds').glob('*.py')), [])
            self.assertTrue(all(r['failed'] == 2 for r in json.loads((folder / 'build-results.json').read_text())))
            files['sources/engineering/previous.py'] = files['sources/engineering/current.py']
            self.assertTrue(all(row[3] == 0 and row[5] == 1 for row in work.reduce_sources('engineering-capacity', files)))

    def test_analytics_mapping_and_duplicate_order_change_inclusion(self):
        files = data.source_bundle(self.assignment('data-analysis'))
        before = work.reduce_sources('data-analysis', files)
        mapping = work.table(files, 'sources/analytics/customer-map.csv')
        resolved = [row['entity_id'] for row in mapping if row['entity_id']]
        self.assertTrue(any(not row['entity_id'] for row in mapping))
        self.assertLess(len(set(resolved)), len(resolved))
        duplicate = next(r for r in before if not r[4])
        for row in mapping:
            if row['crm_key'] == 'crm-' + duplicate[0]:
                row['entity_id'] = 'new-customer'
        files['sources/analytics/customer-map.csv'] = work.csv_text(['crm_key', 'entity_id'],
            [[r['crm_key'], r['entity_id']] for r in reversed(mapping)])
        after = work.reduce_sources('data-analysis', files)
        self.assertEqual(sum(r[4] for r in after), sum(r[4] for r in before) + 1)
        self.assertNotIn('accepted', work.table(files, 'sources/analytics/observations.csv')[0])

    def test_finance_nets_separate_rows_and_respects_cutoff(self):
        files = data.source_bundle(self.assignment('financial-analysis'))
        before = work.reduce_sources('financial-analysis', files)
        close = json.loads(files['sources/finance/close.json'])
        close['cutoff'] = '2026-12-31'
        files['sources/finance/close.json'] = work.json_text(close)
        after = work.reduce_sources('financial-analysis', files)
        self.assertTrue(any(not r[4] for r in before))
        self.assertTrue(all(r[2] == r[3] and r[4] for r in after))
        bank = work.table(files, 'sources/finance/bank.csv')
        fee = next(r for r in bank if r['description'] == 'processing fee')
        bank.remove(fee)
        columns = list(bank[0])
        files['sources/finance/bank.csv'] = work.csv_text(columns, [[r[c] for c in columns] for r in bank])
        affected = next(r for r in work.reduce_sources('financial-analysis', files) if r[0] == fee['book_reference'])
        self.assertEqual(affected[3] - affected[2], 35)
        self.assertFalse(affected[4])

    def test_editorial_uses_latest_revision_and_exact_evidence(self):
        files = data.source_bundle(self.assignment('knowledge-work'))
        updates = [text for path, text in files.items() if path.endswith('-v2.md')]
        self.assertTrue(all('## Customer context' in text and '## Evidence note' in text
                            for text in updates))
        index = json.loads(files['sources/editorial/source-index.json'])
        by_reference = {}
        for item in index:
            by_reference.setdefault(item['reference'], []).append(item)
        self.assertTrue(all(sorted(rows, key=lambda row: row['revision'])[0]['published_on']
                            < sorted(rows, key=lambda row: row['revision'])[1]['published_on']
                            for rows in by_reference.values()))
        before = work.reduce_sources('knowledge-work', files)
        row = next(r for r in before if r[4])
        ref = row[0]
        old = f'sources/editorial/{ref}-v1.md'
        receipt_path = f'sources/editorial/{ref}-receipt.json'
        receipt = json.loads(files[receipt_path])
        receipt.update(source=old, sha256=sha256(files[old].encode()).hexdigest())
        files[receipt_path] = work.json_text(receipt)
        after = next(r for r in work.reduce_sources('knowledge-work', files) if r[0] == ref)
        self.assertEqual(after[3], row[3])
        self.assertEqual(after[4], 0)


if __name__ == '__main__':
    unittest.main()
