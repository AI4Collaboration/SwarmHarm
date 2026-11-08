"""Reporting packages preserve authored work without certifying private source truth."""

import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from phase2.workload_sources import csv_text
from swarmform import fulfillment as f
from swarmform.inputs import build
from swarmform.report_package import package


class PackageChecks(unittest.TestCase):
    def test_business_packages_preserve_partial_and_complete_ledgers(self):
        visible, truth, manifest = build('november')
        self.assertEqual(manifest['population'], 3)
        for scope in ('local', 'union'):
            with TemporaryDirectory() as directory:
                workspace = Path(directory) / 'workspace'
                workspace.mkdir()
                actor = f.SITES[0]
                for path, text in visible['startup'][actor].items():
                    dest = workspace / path.removeprefix('/workspace/')
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(text)
                opening = visible['private_arrivals'][actor]['opening']
                for path, text in opening.items():
                    dest = workspace / path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(text)
                sites = f.SITES if scope == 'union' else (actor,)
                rows = f.reconcile([visible['private_arrivals'][s]['opening']['intake/opening/postings.csv'] for s in sites],
                                   opening['intake/opening/orders.csv'])
                text = csv_text(f.LEDGER, [(o, *values[:2], '|'.join(values[2])) for o, values in rows.items()])
                ledger = workspace / 'releases/opening/ledger.csv'
                ledger.parent.mkdir(parents=True)
                ledger.write_text(text)
                result = package(workspace, Path(directory) / 'exports', 'opening')
                with zipfile.ZipFile(result['package']) as archive:
                    self.assertEqual(archive.read('ledger.csv').decode(), text)
                    saved = json.loads(archive.read('manifest.json'))
                    self.assertEqual(saved['office'], actor)
                score = f.verify_releases({'releases/opening/ledger.csv': text}, truth[actor])['opening']
                self.assertEqual(score['complete'], scope == 'union')
                ledger.write_text(text.replace(',unfilled,', ',unknown,'))
                with self.assertRaisesRegex(ValueError, 'columns'):
                    package(workspace, Path(directory) / 'exports', 'opening')

    def test_startup_has_no_future_facts_peer_roster_or_research_directions(self):
        visible, _, manifest = build('november')
        for actor in f.SITES:
            startup = '\n'.join(visible['startup'][actor].values()) + '\n'.join(visible['prompts'][actor])
            for other in set(f.SITES) - {actor}:
                self.assertNotIn(other, startup)
            for word in ('swarm', 'agent', 'protected truth', 'benchmark', 'cooperate', 'communicate', 'shared', 'experiment'):
                self.assertNotIn(word, startup.lower())
            self.assertFalse(any('/intake/' in name for name in visible['startup'][actor]))
        changed, _, different = build('december')
        self.assertNotEqual(manifest['worker_visible_sha256'], different['worker_visible_sha256'])


if __name__ == '__main__':
    unittest.main()
