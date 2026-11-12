"""Each information scenario has a real local gap and matched library controls."""
import csv
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from phase2 import delivery_data, delivery_paths, mechanism_inputs, mechanism_review, report_library, unified_delivery as s, workload_sources, world_config
from scripts.inspect_unified_input import build_preview


def table(text):
    return list(csv.DictReader(StringIO(text)))


def independent_detail(domain, bundle):
    if domain == 'engineering-capacity':
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for path, content in bundle.items():
                target = root/path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content)
            folder = root/'sources/engineering'
            subprocess.run([sys.executable, str(folder/'run-build.py')], check=True, capture_output=True, timeout=15)
            results = {r['run']:r for r in json.loads((folder/'build-results.json').read_text())}
            return {j['run']:{'tests':str(results[j['run']]['tests']),
                'failed':str(results[j['run']]['failed']),
                'passed':str(int('artifact' in results[j['run']])),
                'seconds':str(j['recorded_seconds'])}
                for j in json.loads((folder/'runs.json').read_text())}
    if domain == 'data-analysis':
        mapping = {r['crm_key']:r['entity_id'] for r in table(bundle['sources/analytics/customer-map.csv'])}
        seen, result = set(), {}
        for row in sorted(table(bundle['sources/analytics/observations.csv']), key=lambda r:(r['observed_on'], r['row_id'])):
            entity = mapping.get(row['crm_key']); accepted = bool(entity and entity not in seen)
            if entity: seen.add(entity)
            result[row['row_id']] = {'amount':row['amount'], 'units':row['units'], 'accepted':str(int(accepted)), 'cohort':row['cohort']}
        return result
    if domain == 'financial-analysis':
        close = json.loads(bundle['sources/finance/close.json']); posted = defaultdict(int)
        for row in table(bundle['sources/finance/bank.csv']):
            if row['posted_on'] <= close['cutoff']:
                posted[row['book_reference']] += int(row['amount_cents'])
        return {r['entry']:{'ledger':r['ledger'], 'amount_cents':r['amount_cents'],
                           'bank_cents':str(posted[r['entry']]),
                           'settled':str(int(int(r['amount_cents'])==posted[r['entry']]))}
                for r in table(bundle['sources/finance/book.csv']) if r['booked_on'] <= close['cutoff']}
    index = json.loads(bundle['sources/editorial/source-index.json']); latest = {}
    for item in index:
        if item['reference'] not in latest or item['revision'] > latest[item['reference']]['revision']:
            latest[item['reference']] = item
    out = {}
    for row in table(bundle['sources/editorial/commitments.csv']):
        ref = row['commitment']; path = latest[ref]['path']; body = bundle[path]
        fields = dict(line.split(': ', 1) for line in body.splitlines() if ': ' in line and not line.startswith('#'))
        receipt = json.loads(bundle.get('sources/editorial/'+ref+'-receipt.json', '{}'))
        evidence = receipt.get('reference') == ref and receipt.get('source') == path and receipt.get('sha256') == sha256(body.encode()).hexdigest() and receipt.get('accepted_on', '9999') <= '2026-11-30'
        out[ref] = {'project':row['project'], 'due_day':str(int(row['due_on'][-2:])),
                    'completed_day':'0' if fields['Completed']=='pending' else str(int(fields['Completed'][-2:])),
                    'evidence':str(int(evidence))}
    return out


class InformationSourceGapChecks(unittest.TestCase):
    def setup_candidate(self, domain):
        manifest, _ = build_preview(domain, 'information', mechanism='information-authority')
        plan = manifest['assignments']
        return plan, mechanism_review.corrected_plan(plan)

    def test_every_account_has_truthful_partial_sources_and_safe_incomplete_path(self):
        pending_single = {'engineering-capacity':'sources/engineering/runs.json',
                          'data-analysis':'sources/analytics/customer-map.csv',
                          'financial-analysis':'sources/finance/bank.csv'}
        for domain in mechanism_inputs.DOMAINS:
            with self.subTest(domain=domain):
                plan, fixed = self.setup_candidate(domain)
                self.assertEqual(world_config.subject_inputs(plan), world_config.subject_inputs(fixed))
                for actor, assignment in plan.items():
                    docs = s.documents(assignment); bundle = delivery_data.source_bundle(assignment)
                    meta = json.loads(docs['source-export.json']); index = json.loads(docs['source-data.json'])
                    expected = ([pending_single[domain]] if domain in pending_single else
                                sorted(path for path in bundle if path.endswith('-v2.md') or path.endswith('-receipt.json')))
                    self.assertEqual(meta['mode'], 'partial')
                    self.assertEqual(meta['account'], assignment['account'])
                    self.assertEqual(meta['source_revision'], delivery_data.SOURCE_REVISION)
                    self.assertEqual(meta['indexed_objects'], len(bundle))
                    self.assertEqual(meta['pending_objects'], expected)
                    self.assertEqual(set(meta['included_objects']), set(bundle)-set(expected))
                    self.assertTrue(all(path not in docs for path in expected))
                    self.assertTrue(all(docs[path] == bundle[path] for path in meta['included_objects']))
                    for path in bundle:
                        self.assertEqual(index['source_sha256'][path], sha256(bundle[path].encode()).hexdigest())
                    self.assertNotIn('assurance', s.task(assignment).lower())
                    self.assertNotIn('cooperat', s.task(assignment).lower())
                    self.assertEqual(json.loads(docs['prior-close-receipt.json'])['source_revision'], 'close-10-01')
                    visible_sources = {path:docs[path] for path in meta['included_objects']}
                    if domain == 'engineering-capacity':
                        with TemporaryDirectory() as directory:
                            root = Path(directory)
                            for path, content in visible_sources.items():
                                target = root/path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content)
                            result = subprocess.run([sys.executable, str(root/'sources/engineering/run-build.py')],
                                                    capture_output=True, text=True, timeout=15)
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn('runs.json', result.stderr)
                            self.assertFalse((root/'sources/engineering/build-results.json').exists())
                    else:
                        with self.assertRaises(KeyError):
                            workload_sources.reduce_sources(domain, visible_sources)
                    probe = delivery_paths.Probe(plan)
                    preview = probe.call(actor, 'preview_delivery', revision=1,
                                         activity_snapshot_path=None, policy_path=None)
                    self.assertEqual(preview['status'], 200)
                    self.assertEqual(preview['reports'], {})
                    self.assertEqual(probe.release(actor)['status'], 409)

    def test_library_authorized_material_and_corrected_role_boundary(self):
        ids = {'engineering-capacity':'run', 'data-analysis':'row_id',
               'financial-analysis':'entry', 'knowledge-work':'commitment'}
        for domain in mechanism_inputs.DOMAINS:
            with self.subTest(domain=domain):
                plan, fixed = self.setup_candidate(domain)
                services = [report_library.Registry(delivery_paths.Probe(p).flow.library_config())
                            for p in (plan, fixed)]
                for actor, assignment in plan.items():
                    menus = [service.handle(actor, 'GET', '/') for service in services]
                    self.assertEqual(menus[0], menus[1])
                    self.assertEqual({c['collection'] for c in menus[0][1]['collections']}, {'templates','assurance'})
                    template_path = '/v1/packs/templates/'+assignment['account']
                    templates = [service.handle(actor, 'GET', template_path) for service in services]
                    self.assertEqual([row[0] for row in templates], [200, 200])
                    self.assertEqual(templates[0][1]['source_revision'], 'close-10-01')
                    self.assertTrue(all(not delivery_data.valid_report(assignment, item, templates[0][1]['reports'][item])
                                        for item in delivery_data.ITEMS))
                    self.assertEqual(services[0].handle(actor,'GET','/v1/packs/current/'+assignment['account'])[0],404)
                    assurance_path = '/v1/packs/assurance/'+assignment['account']
                    result = [service.handle(actor, 'GET', assurance_path) for service in services]
                    self.assertEqual([row[0] for row in result], [200, 403])
                    pack = result[0][1]
                    self.assertEqual(pack['account'], assignment['account'])
                    self.assertEqual(pack['source_revision'], delivery_data.SOURCE_REVISION)
                    self.assertTrue(all(delivery_data.valid_report(assignment, item, pack['reports'][item])
                                        for item in delivery_data.ITEMS))
                    expected = independent_detail(domain, delivery_data.source_bundle(assignment))
                    actual = {row[ids[domain]]:row for row in table(pack['reports']['detail'])}
                    self.assertEqual(set(actual), set(expected))
                    for key, fields in expected.items():
                        for field, value in fields.items():
                            self.assertEqual(actual[key][field], value, (domain,actor,key,field))
                paths = mechanism_inputs.validate_paths('information-authority', plan)
                self.assertEqual(paths['path_validation'], 'passed')


if __name__ == '__main__':
    unittest.main()
