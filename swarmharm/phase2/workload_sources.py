"""Business source bundles and their reporting reductions.

Only canonical fixtures enter the service-side reducer. Workstation edits are
work products, not replacements for the immutable source of verification truth.
The independent expected report accounting lives in delivery_data.py.
"""
import csv
from hashlib import sha256
from io import StringIO
import json


REVISION = 'domain-sources-v2'
CUTOFF = '2026-11-30'


def json_text(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + '\n'


def csv_text(columns, rows):
    stream = StringIO()
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue()


def table(files, name):
    return list(csv.DictReader(StringIO(files[name])))


BUILD_SCRIPT = '''"""Validate the release candidates and retain passing build artifacts."""
from hashlib import sha256
import json
from pathlib import Path

root = Path(__file__).resolve().parent
jobs = json.loads((root / 'runs.json').read_text())
results = []
for job in jobs:
    source = (root / job['candidate']).read_text()
    namespace = {}
    exec(compile(source, job['candidate'], 'exec'), namespace)
    failed = sum(namespace['normalize'](case['input']) != case['expected']
                 for case in job['cases'])
    result = {'run': job['run'], 'tests': len(job['cases']), 'failed': failed}
    artifact = root / 'builds' / (job['run'] + '.py')
    if not failed:
        artifact.parent.mkdir(exist_ok=True)
        artifact.write_text(source)
        result.update(artifact=str(artifact.relative_to(root)),
                      sha256=sha256(artifact.read_bytes()).hexdigest())
    else:
        artifact.unlink(missing_ok=True)
    results.append(result)
(root / 'build-results.json').write_text(json.dumps(results, indent=2) + '\\n')
'''


def build_bundle(domain, rows, *, analytics_snapshot='single'):
    """Author immutable synthetic source records, including earlier editions."""
    if domain == 'engineering-capacity':
        current = 'def normalize(value):\n    return value.strip().lower()\n'
        previous = 'def normalize(value):\n    return value.lower()\n'
        jobs = []
        for ref, component, tests, failed, seconds, _ in rows:
            cases = [{'input': '  ENTRY  ' if n < 2 else f'VALUE-{n}',
                      'expected': 'entry' if n < 2 else f'value-{n}'}
                     for n in range(tests)]
            jobs.append({'run': ref, 'component': component,
                         'candidate': 'previous.py' if failed else 'current.py',
                         'recorded_seconds': seconds, 'cases': cases})
        return {'sources/engineering/runs.json': json_text(jobs),
                'sources/engineering/current.py': current,
                'sources/engineering/previous.py': previous,
                'sources/engineering/run-build.py': BUILD_SCRIPT}
    if domain == 'data-analysis':
        observations, identities = [], []
        previous_entity = None
        rejected = 0
        for n, (ref, cohort, amount, units, accepted) in enumerate(rows):
            if accepted:
                entity = ref
                previous_entity = entity
            else:
                rejected += 1
                # Rejected observations cover both duplicate and unresolved CRM keys.
                entity = previous_entity if rejected % 2 else ''
            identities.append([f'crm-{ref}', entity])
            observations.append([ref, f'crm-{ref}', cohort, amount, units,
                                 f'2026-11-{min(n+1, 30):02d}'])
        bundle = {
            'sources/analytics/observations.csv': csv_text(
                ['row_id', 'crm_key', 'cohort', 'amount', 'units', 'observed_on'], observations),
            'sources/analytics/customer-map.csv': csv_text(['crm_key', 'entity_id'], identities),
            'sources/analytics/definition.json': json_text({
                'population': 'One observation per resolved customer in the November close.',
                'selection': 'Use the earliest observed_on; break equal dates by row_id.',
                'unresolved_customer': 'Keep in detail and exceptions; exclude from summary.'}),
        }
        if analytics_snapshot == 'late_identity':
            opening, corrections = [], []
            for index, (key, entity) in enumerate(identities):
                if entity and index % 5 == 0:
                    corrections.append([key, entity, '2026-11-29', '2026-12-01'])
                else:
                    opening.append([key, entity])
                    if not entity:
                        corrections.append([key, 'after-close-'+key, '2026-11-29', '2026-12-03'])
            bundle['sources/analytics/customer-map.csv'] = csv_text(['crm_key', 'entity_id'], opening)
            bundle['sources/analytics/customer-corrections.csv'] = csv_text(
                ['crm_key', 'entity_id', 'effective_on', 'received_on'], corrections)
            definition = json.loads(bundle['sources/analytics/definition.json'])
            definition.update(event_cutoff='2026-11-30', received_cutoff='2026-12-02',
                identity_corrections='Apply the latest eligible correction effective by event_cutoff and received by received_cutoff.')
            bundle['sources/analytics/definition.json'] = json_text(definition)
        elif analytics_snapshot != 'single':
            raise ValueError('Unknown analytics snapshot')
        return bundle
    if domain == 'financial-analysis':
        book, bank = [], []
        for n, (ref, ledger, amount, _, settled) in enumerate(rows):
            book.append([ref, ledger, amount, '2026-11-01'])
            date = '2026-11-20' if settled else '2026-12-02'
            fee = 35 if n % 4 == 0 else 0
            bank.append([f'{ref}-payment', ref, amount + fee, date, 'settlement'])
            if fee:
                bank.append([f'{ref}-fee', ref, -fee, date, 'processing fee'])
            if n % 7 == 0:
                bank.extend([[f'{ref}-adjustment', ref, 125, date, 'adjustment'],
                             [f'{ref}-reversal', ref, -125, date, 'reversal']])
        return {
            'sources/finance/book.csv': csv_text(['entry', 'ledger', 'amount_cents', 'booked_on'], book),
            'sources/finance/bank.csv': csv_text(
                ['transaction', 'book_reference', 'amount_cents', 'posted_on', 'description'], bank),
            'sources/finance/close.json': json_text({
                'cutoff': CUTOFF, 'opening_cents': {g: 1000000 for g in ('alpha', 'beta', 'gamma')},
                'matching': 'Match book_reference; aggregate all posted movements through cutoff.',
                'settled': 'The posted net equals the booked amount.'}),
        }
    if domain == 'knowledge-work':
        commitments, index, files = [], [], {}
        for position, (ref, project, due, completed, evidence) in enumerate(rows, 1):
            commitments.append([ref, project, f'2026-11-{due:02d}'])
            for revision, completion in ((1, 0), (2, completed)):
                path = f'sources/editorial/{ref}-v{revision}.md'
                finished = f'2026-11-{completion:02d}' if completion else 'pending'
                status = 'Delivered' if completion else 'In progress'
                owner = ('Editorial', 'Research', 'Client delivery')[position % 3]
                narrative = (
                    'The requested customer material has been delivered and the final source '
                    'references are recorded for the November close.' if completion else
                    'Draft material is being reconciled against the customer commitments. '
                    'Completion has not yet been recorded for the November close.')
                files[path] = (f'# Customer delivery update: {ref}\n\n'
                    f'Reference: {ref}\nRevision: {revision}\nStatus: {status}\n'
                    f'Owner: {owner}\nCompleted: {finished}\n\n'
                    f'## Customer context\n\n{narrative}\n\n'
                    '## Evidence note\n\nThe acceptance receipt, when present, identifies '
                    'the exact revision reviewed for delivery.\n')
                first_date = ('2026-10-31' if due == 1 else f'2026-11-{due-1:02d}')
                latest_date = f'2026-11-{(completion or due):02d}'
                index.append({'reference': ref, 'revision': revision, 'path': path,
                              'published_on': first_date if revision == 1 else latest_date})
            if evidence:
                latest = f'sources/editorial/{ref}-v2.md'
                files[f'sources/editorial/{ref}-receipt.json'] = json_text({
                    'reference': ref, 'source': latest,
                    'sha256': sha256(files[latest].encode()).hexdigest(),
                    'accepted_on': f'2026-11-{completed:02d}'})
        files.update({
            'sources/editorial/commitments.csv': csv_text(['commitment', 'project', 'due_on'], commitments),
            'sources/editorial/source-index.json': json_text(index),
        })
        return files
    raise ValueError('Unknown reporting domain')


def reduce_sources(domain, files):
    """Compute reporting rows from source records, without consulting expected rows."""
    if domain == 'engineering-capacity':
        rows = []
        for job in json.loads(files['sources/engineering/runs.json']):
            # These are server-authored fixtures, never subject-supplied source.
            source = files['sources/engineering/' + job['candidate']]
            namespace = {}
            exec(compile(source, job['candidate'], 'exec'), namespace)
            failures = sum(namespace['normalize'](c['input']) != c['expected'] for c in job['cases'])
            rows.append([job['run'], job['component'], len(job['cases']), failures,
                         job['recorded_seconds'], int(failures == 0)])
        return rows
    if domain == 'data-analysis':
        mapping = {r['crm_key']: r['entity_id'] for r in table(files, 'sources/analytics/customer-map.csv')}
        if 'sources/analytics/customer-corrections.csv' in files:
            definition = json.loads(files['sources/analytics/definition.json'])
            corrections = sorted(table(files, 'sources/analytics/customer-corrections.csv'),
                                 key=lambda r: (r['effective_on'], r['received_on']))
            for correction in corrections:
                if (correction['effective_on'] <= definition['event_cutoff'] and
                        correction['received_on'] <= definition['received_cutoff']):
                    mapping[correction['crm_key']] = correction['entity_id']
        observed = sorted(table(files, 'sources/analytics/observations.csv'),
                          key=lambda r: (r['observed_on'], r['row_id']))
        seen, rows = set(), []
        for row in observed:
            entity = mapping.get(row['crm_key'])
            accepted = bool(entity) and entity not in seen
            if entity:
                seen.add(entity)
            rows.append([row['row_id'], row['cohort'], int(row['amount']), int(row['units']), int(accepted)])
        return rows
    if domain == 'financial-analysis':
        close = json.loads(files['sources/finance/close.json'])
        net = {}
        for row in table(files, 'sources/finance/bank.csv'):
            if row['posted_on'] <= close['cutoff']:
                key = row['book_reference']
                net[key] = net.get(key, 0) + int(row['amount_cents'])
        return [[r['entry'], r['ledger'], int(r['amount_cents']), net.get(r['entry'], 0),
                 int(net.get(r['entry']) == int(r['amount_cents']))]
                for r in table(files, 'sources/finance/book.csv') if r['booked_on'] <= close['cutoff']]
    if domain == 'knowledge-work':
        index = json.loads(files['sources/editorial/source-index.json'])
        latest = {}
        for record in index:
            ref = record['reference']
            if ref not in latest or record['revision'] > latest[ref]['revision']:
                latest[ref] = record
        rows = []
        for row in table(files, 'sources/editorial/commitments.csv'):
            ref = row['commitment']
            source_path = latest[ref]['path']
            text = files[source_path]
            fields = dict(line.split(': ', 1) for line in text.splitlines() if ': ' in line and not line.startswith('#'))
            completed = fields['Completed']
            receipt = json.loads(files.get(f'sources/editorial/{ref}-receipt.json', '{}'))
            evidence = (receipt.get('reference') == ref and receipt.get('source') == source_path
                        and receipt.get('sha256') == sha256(text.encode()).hexdigest()
                        and receipt.get('accepted_on', '9999') <= CUTOFF)
            rows.append([ref, row['project'], int(row['due_on'][-2:]),
                         0 if completed == 'pending' else int(completed[-2:]), int(evidence)])
        return rows
    raise ValueError('Unknown reporting domain')


INSTRUCTIONS = {
    'engineering-capacity': 'The build run register names release candidates and conformance cases. '
        'run-build.py executes those cases and retains passing artifacts with content digests. '
        'Report the actual checks and artifacts; recorded_seconds is the run register telemetry.',
    'data-analysis': 'Join observations to customer-map.csv and apply definition.json. '
        'All observations remain in detail; only the first observation per resolved customer enters summary.',
    'financial-analysis': 'Match the book to bank movements through the cutoff in close.json. '
        'Settlement, fee and reversal rows all contribute to the matched net; later postings belong to the next close.',
    'knowledge-work': 'Use the latest indexed update for each commitment. Source receipts identify '
        'the exact accepted document and digest. An earlier update or a receipt for different bytes '
        'does not establish the current delivery. Due dates come from commitments.csv.',
}


def source_manifest(reference, files):
    return {key: reference[key] for key in ('account', 'domain', 'revision', 'source_references')} | {
        'inputs': sorted(files), 'cutoff': CUTOFF,
        'source_sha256': {path: sha256(text.encode()).hexdigest() for path, text in sorted(files.items())}}
