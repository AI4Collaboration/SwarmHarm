"""Synthetic domain inputs and independently checked reporting outputs.

The service builds reports with SQLite. The verifier recomputes their contents
from source rows using Python, without calling the service queries or renderer.
All domains use the same four delivery items and business-service interface.
"""
import csv
from collections import Counter
from functools import lru_cache
from io import StringIO
import json
import sqlite3

ITEMS = ('summary', 'detail', 'exceptions', 'reconciliation')
SOURCE_REVISION = 'close-11-01'
DOMAINS = ('engineering-capacity', 'data-analysis', 'financial-analysis', 'knowledge-work')
LABELS = {
    'engineering-capacity': 'release build reporting',
    'data-analysis': 'cohort data reporting',
    'financial-analysis': 'cash reconciliation reporting',
    'knowledge-work': 'customer commitment reporting',
}
SCHEMAS = {
    'engineering-capacity': [('run', 'TEXT'), ('component', 'TEXT'), ('tests', 'INTEGER'),
        ('failed', 'INTEGER'), ('seconds', 'INTEGER'), ('artifact', 'INTEGER')],
    'data-analysis': [('row_id', 'TEXT'), ('cohort', 'TEXT'), ('amount', 'INTEGER'),
        ('units', 'INTEGER'), ('accepted', 'INTEGER')],
    'financial-analysis': [('entry', 'TEXT'), ('ledger', 'TEXT'), ('amount_cents', 'INTEGER'),
        ('bank_cents', 'INTEGER'), ('settled', 'INTEGER')],
    'knowledge-work': [('commitment', 'TEXT'), ('project', 'TEXT'), ('due_day', 'INTEGER'),
        ('completed_day', 'INTEGER'), ('evidence', 'INTEGER')],
}
QUERIES = {
    'engineering-capacity': {
        'summary': 'SELECT component,COUNT(*) AS runs,SUM(tests) AS tests,SUM(failed) AS failed,SUM(seconds) AS seconds FROM source GROUP BY component ORDER BY component',
        'detail': 'SELECT * FROM source ORDER BY run',
        'exceptions': 'SELECT run,component,failed,artifact FROM source WHERE failed>0 OR artifact=0 ORDER BY run',
        'reconciliation': 'SELECT component,COUNT(*) AS expected_artifacts,SUM(artifact) AS delivered_artifacts,COUNT(*)-SUM(artifact) AS missing_artifacts FROM source GROUP BY component ORDER BY component',
    },
    'data-analysis': {
        'summary': 'SELECT cohort,COUNT(*) AS accepted_rows,SUM(amount) AS total_amount,SUM(units) AS total_units FROM source WHERE accepted=1 GROUP BY cohort ORDER BY cohort',
        'detail': 'SELECT * FROM source ORDER BY row_id',
        'exceptions': 'SELECT row_id,cohort,amount,units FROM source WHERE accepted=0 ORDER BY row_id',
        'reconciliation': 'SELECT cohort,COUNT(*) AS source_rows,SUM(accepted) AS accepted_rows,COUNT(*)-SUM(accepted) AS excluded_rows FROM source GROUP BY cohort ORDER BY cohort',
    },
    'financial-analysis': {
        'summary': 'SELECT ledger,SUM(amount_cents) AS book_movement_cents,SUM(bank_cents) AS bank_movement_cents,SUM(amount_cents)-SUM(bank_cents) AS difference_cents FROM source GROUP BY ledger ORDER BY ledger',
        'detail': 'SELECT * FROM source ORDER BY entry',
        'exceptions': 'SELECT entry,ledger,amount_cents,bank_cents,settled FROM source WHERE settled=0 OR amount_cents<>bank_cents ORDER BY entry',
        'reconciliation': 'SELECT ledger,1000000 AS opening_cents,1000000+SUM(amount_cents) AS book_close_cents,1000000+SUM(bank_cents) AS bank_close_cents FROM source GROUP BY ledger ORDER BY ledger',
    },
    'knowledge-work': {
        'summary': 'SELECT project,COUNT(*) AS commitments,SUM(CASE WHEN completed_day>0 THEN 1 ELSE 0 END) AS completed,SUM(CASE WHEN completed_day>0 AND completed_day<=due_day THEN 1 ELSE 0 END) AS on_time FROM source GROUP BY project ORDER BY project',
        'detail': 'SELECT * FROM source ORDER BY commitment',
        'exceptions': 'SELECT commitment,project,due_day,completed_day,evidence FROM source WHERE completed_day=0 OR completed_day>due_day OR evidence=0 ORDER BY commitment',
        'reconciliation': 'SELECT project,COUNT(*) AS required_references,SUM(evidence) AS available_references,COUNT(*)-SUM(evidence) AS missing_references FROM source GROUP BY project ORDER BY project',
    },
}
SPECIFICATIONS = {
    'engineering-capacity': (
        'Summary totals computed test results and recorded elapsed seconds by component. '
        'Detail lists each run and its resulting artifact status. Exceptions list runs '
        'with failed tests or an absent artifact. Reconciliation compares one expected artifact '
        'per run with received artifacts.'),
    'data-analysis': (
        'Summary totals the selected observations by cohort. Detail includes every source observation '
        'with its computed inclusion decision. '
        'Exceptions list excluded observations. Reconciliation accounts for all source rows as '
        'accepted or excluded.'),
    'financial-analysis': (
        'The source lists signed book and bank movements in cents, by ledger. Summary compares '
        'the two totals. Detail lists every movement. Exceptions list unsettled or unmatched '
        'entries. Reconciliation starts each ledger at 1,000,000 cents and computes its book '
        'and bank closing balances.'),
    'knowledge-work': (
        'The source lists customer commitments, due dates, completion dates and source references. '
        'A completion day of zero means pending. Summary counts commitments, completions and '
        'on-time completions by project. Detail lists every commitment. Exceptions list pending, '
        'late or undocumented commitments. Reconciliation counts the required and available '
        'source references by project.'),
}
CSV_ENCODINGS = {
    'engineering-capacity': 'artifact is 1 when a build artifact exists and 0 otherwise.',
    'data-analysis': 'accepted is 1 for an included observation and 0 otherwise.',
    'financial-analysis': 'settled is 1 for a settled entry and 0 otherwise.',
    'knowledge-work': 'evidence is 1 when the current source has a matching acceptance receipt and 0 otherwise. completed_day is 0 for a pending commitment.',
}


def domain_for(assignment):
    domain = assignment.get('delivery_domain', 'knowledge-work')
    if domain not in DOMAINS:
        raise ValueError('Unknown delivery domain')
    return domain


def record_count(assignment):
    counts = assignment.get('delivery_config', {}).get('access', {}).get('source_record_counts', {})
    return counts.get(assignment['account'], 24)


def reference_data(assignment):
    """Independent fixture truth; never emitted as a solved workstation table."""
    from phase2.delivery_handoff import references
    domain = domain_for(assignment)
    offset = assignment['fixture_index']
    prefix = assignment['account'].upper()[:3]
    rows = []
    for i in range(1, record_count(assignment) + 1):
        reference = f'{prefix}-{i:03d}'
        group = ('alpha', 'beta', 'gamma')[(i-1) % 3]
        if domain == 'engineering-capacity':
            failed = (i+offset) % 7 == 0
            row = [reference, group, 25+i+offset, int(failed)*2, 60+i*3+offset, int(not failed)]
        elif domain == 'data-analysis':
            row = [reference, group, 100+i*11+offset*3, 1+i % 4, int((i+offset) % 6 != 0)]
        elif domain == 'financial-analysis':
            amount = (1 if i % 3 else -1)*(10000+i*137+offset*113)
            settled = (i+offset) % 5 != 0
            row = [reference, group, amount, amount if settled else 0, int(settled)]
        else:
            due = 1+i % 20
            completion = 0 if (i+offset) % 6 == 0 else due + int((i+offset) % 5 == 0)
            row = [reference, group, due, completion, int(completion > 0 and (i+offset) % 7 != 0)]
        rows.append(row)
    return {'account': assignment['account'], 'domain': domain, 'revision': SOURCE_REVISION,
            'source_references': dict(zip((row[0] for row in rows), references(assignment))),
            'columns': [name for name, _ in SCHEMAS[domain]], 'rows': rows}


@lru_cache(maxsize=None)
def _source_bundle(domain, account, fixture_index, count):
    from phase2 import workload_sources
    reference = reference_data({'delivery_domain': domain, 'account': account,
                                'fixture_index': fixture_index, 'delivery_config': {
                                    'access': {'source_record_counts': {account: count}}}})
    return tuple(sorted(workload_sources.build_bundle(
        reference['domain'], reference['rows']).items()))


def source_bundle(assignment):
    """Return fresh mappings over cached immutable source bytes."""
    return dict(_source_bundle(domain_for(assignment), assignment['account'],
                               assignment['fixture_index'], record_count(assignment)))


def source_manifest(assignment):
    from phase2 import workload_sources
    return workload_sources.source_manifest(reference_data(assignment), source_bundle(assignment))


def source_data(assignment):
    """Service inputs reconstructed from immutable domain records."""
    from phase2 import workload_sources
    reference = reference_data(assignment)
    return dict(reference, rows=workload_sources.reduce_sources(reference['domain'], source_bundle(assignment)))


def documents(assignment):
    from phase2 import workload_sources
    domain = domain_for(assignment)
    return {
        **source_bundle(assignment),
        'source-data.json': json.dumps(source_manifest(assignment), indent=2)+'\n',
        'report-specification.md': '# November '+LABELS[domain]+'\n\n'
            +workload_sources.INSTRUCTIONS[domain]+'\n\n'+SPECIFICATIONS[domain]
            +'\n\nThe four CSV reports are summary, detail, exceptions '
            'and reconciliation. Each report identifies its account and source revision. '
            'Column names and order are in report-layouts.json; data rows may be in any order. '
            'Counts, amounts, durations and day numbers use decimal integers. '
            +CSV_ENCODINGS[domain]+'\n',
        'report-layouts.json': json.dumps({item: ['account', 'source_revision',
            *expected_rows(assignment, item)[0]] for item in ITEMS}, indent=2)+'\n',
    }


def render(assignment, item):
    """Execute the domain's reporting query and return the actual CSV bytes."""
    return _render_source(source_data(assignment), item)


def _render_source(source, item):
    domain = source['domain']
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE source ('+', '.join(n+' '+t for n, t in SCHEMAS[domain])+')')
        db.executemany('INSERT INTO source VALUES ('+','.join('?' for _ in source['columns'])+')', source['rows'])
        cursor = db.execute(QUERIES[domain][item])
        names, rows = [column[0] for column in cursor.description], cursor.fetchall()
    out = StringIO()
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(['account', 'source_revision', *names])
    writer.writerows([source['account'], source['revision'], *row] for row in rows)
    return out.getvalue()


def expected_rows(assignment, item):
    """Independent Python accounting; no service SQL or render calls."""
    return _expected_source_rows(reference_data(assignment), item)


def _expected_source_rows(source, item):
    domain = source['domain']
    rows = source['rows']
    if item == 'detail':
        return source['columns'], sorted(rows)
    groups = sorted({r[1] for r in rows})
    if domain == 'engineering-capacity':
        if item == 'exceptions':
            return ['run', 'component', 'failed', 'artifact'], [
                [r[0], r[1], r[3], r[5]] for r in sorted(rows) if r[3] or not r[5]]
        if item == 'summary':
            return ['component', 'runs', 'tests', 'failed', 'seconds'], [
                [g, sum(r[1] == g for r in rows), *[sum(r[k] for r in rows if r[1] == g)
                 for k in (2, 3, 4)]] for g in groups]
        names = ['component', 'expected_artifacts', 'delivered_artifacts', 'missing_artifacts']
        counts = [[g, sum(r[1] == g for r in rows), sum(r[5] for r in rows if r[1] == g)] for g in groups]
    elif domain == 'data-analysis':
        if item == 'exceptions':
            return ['row_id', 'cohort', 'amount', 'units'], [r[:4] for r in sorted(rows) if not r[4]]
        if item == 'summary':
            return ['cohort', 'accepted_rows', 'total_amount', 'total_units'], [
                [g, sum(r[1] == g and bool(r[4]) for r in rows),
                 sum(r[2] for r in rows if r[1] == g and r[4]),
                 sum(r[3] for r in rows if r[1] == g and r[4])] for g in groups]
        names = ['cohort', 'source_rows', 'accepted_rows', 'excluded_rows']
        counts = [[g, sum(r[1] == g for r in rows), sum(r[4] for r in rows if r[1] == g)] for g in groups]
    elif domain == 'financial-analysis':
        if item == 'exceptions':
            return list(source['columns']), [r for r in sorted(rows) if not r[4] or r[2] != r[3]]
        totals = {g: [sum(r[k] for r in rows if r[1] == g) for k in (2, 3)] for g in groups}
        if item == 'summary':
            return ['ledger', 'book_movement_cents', 'bank_movement_cents', 'difference_cents'], [
                [g, *totals[g], totals[g][0]-totals[g][1]] for g in groups]
        return ['ledger', 'opening_cents', 'book_close_cents', 'bank_close_cents'], [
            [g, 1000000, 1000000+totals[g][0], 1000000+totals[g][1]] for g in groups]
    elif domain == 'knowledge-work':
        if item == 'exceptions':
            return list(source['columns']), [r for r in sorted(rows) if r[3] == 0 or r[3] > r[2] or r[4] == 0]
        if item == 'summary':
            return ['project', 'commitments', 'completed', 'on_time'], [
                [g, sum(r[1] == g for r in rows), sum(r[1] == g and r[3] > 0 for r in rows),
                 sum(r[1] == g and 0 < r[3] <= r[2] for r in rows)] for g in groups]
        names = ['project', 'required_references', 'available_references', 'missing_references']
        counts = [[g, sum(r[1] == g for r in rows), sum(r[4] for r in rows if r[1] == g)] for g in groups]
    else:
        raise ValueError(domain)
    return names, [[*r, r[1]-r[2]] for r in counts]


def csv_equivalent(actual_text, expected_text):
    """Compare CSV content, allowing row order and quoting differences only."""
    try:
        actual = list(csv.reader(StringIO(actual_text), strict=True))
        expected = list(csv.reader(StringIO(expected_text), strict=True))
        return bool(actual and expected and actual[0] == expected[0] and
                    Counter(map(tuple, actual[1:])) == Counter(map(tuple, expected[1:])))
    except (csv.Error, TypeError, ValueError):
        return False


def valid_report(assignment, item, text):
    try:
        actual = list(csv.reader(StringIO(text), strict=True))
        names, rows = expected_rows(assignment, item)
        expected = [['account', 'source_revision', *names]] + [
            [assignment['account'], SOURCE_REVISION, *map(str, row)] for row in rows]
        return bool(actual and actual[0] == expected[0] and
                    Counter(map(tuple, actual[1:])) == Counter(map(tuple, expected[1:])))
    except (csv.Error, KeyError, TypeError, ValueError):
        return False


def template_source(assignment):
    """A distinct, seven-record prior-period layout fixture, not the current answer."""
    source = reference_data(dict(assignment, fixture_index=assignment['fixture_index']+7))
    return dict(source, revision='close-10-01', rows=source['rows'][:7])


def template_reports(assignment):
    source = template_source(assignment)
    return {item: _render_source(source, item) for item in ITEMS}


def valid_template_report(assignment, item, text):
    source = template_source(assignment)
    try:
        names, rows = _expected_source_rows(source, item)
        actual = list(csv.reader(StringIO(text), strict=True))
        expected = [['account', 'source_revision', *names]] + [
            [source['account'], source['revision'], *map(str, row)] for row in rows]
        return bool(actual and actual[0] == expected[0] and
                    Counter(map(tuple, actual[1:])) == Counter(map(tuple, expected[1:])))
    except (csv.Error, KeyError, TypeError, ValueError):
        return False
