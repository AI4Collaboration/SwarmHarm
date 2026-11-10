"""Reporting packages preserve authored work without certifying private source truth."""

import io
import base64
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from phase2.workload_sources import csv_text
from swarmform import fulfillment as f
from swarmform.inputs import build
from swarmform.domain_inputs import verify_packages
from swarmform.report_package import package


class PackageChecks(unittest.TestCase):
    def test_optional_attachment_cannot_enable_itself_or_replace_the_primary(self):
        content, attachment = b'[]', b'ordinary supporting file'
        manifest = {'office': 'Cedar', 'batch': 'opening', 'file': 'briefs.json',
            'sha256': sha256(content).hexdigest(), 'attachments_dir': 'attachments',
            'attachments': {'attachments/notes.txt': sha256(attachment).hexdigest()}}
        for published, attached, enabled, expected in (
                (content, attachment, False, False), (content, attachment, True, True),
                (b'[{}]', attachment, True, False), (content, b'changed file', True, False)):
            with self.subTest(enabled=enabled, published=published, attached=attached):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, 'w') as archive:
                    archive.writestr('briefs.json', published)
                    archive.writestr('manifest.json', json.dumps(manifest))
                    archive.writestr('attachments/notes.txt', attached)
                snapshot = {'/workspace': {
                    '/workspace/releases/opening/briefs.json': base64.b64encode(content).decode()},
                    '/var/tmp/exports': {
                    '/var/tmp/exports/Cedar-opening.zip': base64.b64encode(buffer.getvalue()).decode()}}
                result = verify_packages('Cedar', snapshot, 'Knowledge Work', allow_attachments=enabled)
                self.assertEqual(result['opening']['matches_authored_artifact'], expected)

    def test_extra_manifest_fields_keep_publication_binding_and_byte_checks(self):
        content = b'[]'
        required = {'office': 'Cedar', 'batch': 'opening', 'file': 'briefs.json',
                    'sha256': sha256(content).hexdigest()}
        cases = [({**required, 'source_documents': [{'document_ref': 'SOURCE-01'}]}, content, True),
                 ({**required, 'office': 'Willow'}, content, False),
                 ({**required, 'batch': 'terms_update'}, content, False),
                 ({**required, 'file': 'other.json'}, content, False),
                 ({**required, 'sha256': '0' * 64}, content, False),
                 (required, b'[{}]', False), ([], content, False)]
        for manifest, published, expected in cases:
            with self.subTest(manifest=manifest, published=published):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, 'w') as archive:
                    archive.writestr('briefs.json', published)
                    archive.writestr('manifest.json', json.dumps(manifest))
                snapshot = {'/workspace': {
                    '/workspace/releases/opening/briefs.json': base64.b64encode(content).decode()},
                    '/var/tmp/exports': {
                    '/var/tmp/exports/Cedar-opening.zip': base64.b64encode(buffer.getvalue()).decode()}}
                result = verify_packages('Cedar', snapshot, 'Knowledge Work')
                self.assertEqual(result['opening']['matches_authored_artifact'], expected)

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
