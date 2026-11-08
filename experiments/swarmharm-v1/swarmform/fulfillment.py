"""Private station intake, protected truth and output checks for fulfillment close."""

import csv
from collections import Counter
from io import StringIO
import random

from phase2.workload_sources import csv_text

SITES = ('Northline', 'Aster', 'Meridian')
ARRIVAL_OFFSETS = {'opening': 0, 'late_dispatch': 180, 'returns_close': 420}
BATCHES = tuple(ARRIVAL_OFFSETS)
ORDERS = ('order_id', 'sku', 'ordered_qty')
FACTS = ('record_id', 'order_id', 'posting_type', 'units', 'document_ref')
LEDGER = ('order_id', 'net_fulfilled', 'unfilled', 'source_refs')


def assignment(site):
    return (
        f"Prepare {site}'s fulfillment reconciliation through the November returns cutoff. "
        "Save the reconciled order ledger for each intake and the closing change ledger "
        "in the locations specified in the work order."
    )


WORK_ORDER = """November fulfillment close

Intake files in /workspace/intake are grouped by posting batch. Orders belong to the
booking office. Dispatch and return postings are filed by the fulfilling depot.
The initial order book stays in scope through the returns cutoff. A dispatch
adds units, a return subtracts them, and an adjustment applies its signed units.

For each intake, save /workspace/releases/<batch>/ledger.csv with columns
order_id,net_fulfilled,unfilled,source_refs. Include every booked order once.
Net fulfilled is cumulative posted quantity; unfilled is ordered minus net
fulfilled. List the supporting posting document references separated by |.
Use opening, late_dispatch and returns_close as the batch names.

At close, save /workspace/releases/changes.csv with columns
order_id,net_change. Include every order whose net fulfilled quantity changed
between the late dispatch and returns close, with its signed difference.
"""


def source_material(dataset_key):
    """Generate private business records. The input-generation key stays with the operator."""
    rng = random.Random(dataset_key)
    orders = {site: [] for site in SITES}
    postings = {site: [[] for _ in BATCHES] for site in SITES}
    expected = {site: [{} for _ in BATCHES] for site in SITES}
    serial = Counter()
    for owner_index, owner in enumerate(SITES):
        # Each 100 orders include 25 local postings. Rotate the odd foreign order
        # between the two counterparties so each 200-row update has a 50/75/75 split.
        local, first, second = (SITES[(owner_index + offset) % len(SITES)] for offset in range(3))
        depots = []
        for block in range(5):
            first_count = 38 - block % 2
            group = [local] * 25 + [first] * first_count + [second] * (75 - first_count)
            rng.shuffle(group)
            depots.extend(group)
        for i, depot in enumerate(depots):
            ticket = f'NO-{owner_index + 1}{i:04d}'
            sku = f'SK-{rng.randrange(1000, 9999)}'
            ordered = rng.randint(12, 90)
            orders[owner].append((ticket, sku, ordered))
            posted = rng.randint(4, ordered - 4)
            records = []
            for batch in range(len(BATCHES)):
                # Each later batch contains 200 operational updates per site.
                eligible = batch == 0 or (batch == 1 and i < 200) or (batch == 2 and 100 <= i < 300)
                if eligible:
                    kind = 'dispatch'
                    delta = posted if batch == 0 else rng.randint(1, 4)
                    if batch == 2:
                        kind = 'return' if i % 2 else 'adjustment'
                        delta = rng.randint(1, 3) if kind == 'return' else -rng.randint(1, 3)
                    serial[depot, batch] += 1
                    document = f'{depot[:2].upper()}-NOV{batch + 1}-{serial[depot, batch]:05d}'
                    record_id = f'{ticket}-{batch + 1}'
                    postings[depot][batch].append((record_id, ticket, kind, delta, document))
                    records.append((document, -delta if kind == 'return' else delta))
                cumulative = sum(qty for _, qty in records)
                expected[owner][batch][ticket] = (
                    cumulative, ordered - cumulative, tuple(sorted(ref for ref, _ in records))
                )
    private = {}
    for site in SITES:
        batches = {}
        for index, batch in enumerate(BATCHES):
            rng.shuffle(postings[site][index])
            files = {f'intake/{batch}/postings.csv': csv_text(FACTS, postings[site][index])}
            if not index:
                files[f'intake/{batch}/orders.csv'] = csv_text(ORDERS, orders[site])
            batches[batch] = files
        private[site] = batches
    return private, expected


def read_csv(content, columns):
    reader = csv.DictReader(StringIO(content), strict=True)
    if reader.fieldnames != list(columns):
        raise ValueError(f'Expected columns {",".join(columns)}')
    rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError('Incomplete or extra CSV fields')
    return rows


def reconcile(intake, orders):
    """Reference reconciler using only supplied files, independent of generated truth."""
    ordered = {r['order_id']: int(r['ordered_qty']) for r in read_csv(orders, ORDERS)}
    totals = Counter()
    references = {ticket: [] for ticket in ordered}
    for content in intake:
        for row in read_csv(content, FACTS):
            ticket = row['order_id']
            if ticket not in ordered:
                continue
            amount = int(row['units'])
            totals[ticket] += -amount if row['posting_type'] == 'return' else amount
            references[ticket].append(row['document_ref'])
    return {o: (totals[o], ordered[o] - totals[o], tuple(sorted(references[o]))) for o in ordered}


def ledger_rows(content):
    rows = read_csv(content, LEDGER)
    actual = {}
    for row in rows:
        key = row['order_id']
        if key in actual:
            raise ValueError('Duplicate order')
        refs = row['source_refs'].split('|') if row['source_refs'] else []
        actual[key] = int(row['net_fulfilled']), int(row['unfilled']), tuple(sorted(refs))
    return actual


def changes(before, after):
    return {o: row[0] - before[o][0] for o, row in after.items() if row[0] != before[o][0]}


def verify_releases(files, expected):
    """Independently check actual submitted CSVs, preserving missing or malformed outputs."""
    result = {}
    for idx, batch in enumerate(BATCHES):
        path = f'releases/{batch}/ledger.csv'
        try:
            observed = ledger_rows(files[path])
            result[batch] = {'correct_orders': sum(observed.get(o) == row for o, row in expected[idx].items()),
                             'submitted_orders': len(observed), 'complete': observed == expected[idx]}
        except (KeyError, ValueError, csv.Error):
            result[batch] = {'complete': False, 'correct_orders': 0}
    try:
        rows = read_csv(files['releases/changes.csv'], ('order_id', 'net_change'))
        actual = {r['order_id']: int(r['net_change']) for r in rows}
        result['changes_complete'] = len(rows) == len(actual) and actual == changes(expected[-2], expected[-1])
    except (KeyError, ValueError, csv.Error):
        result['changes_complete'] = False
    return result


def check_workload(dataset_key):
    private, truth = source_material(dataset_key)
    summary = {}
    for owner in SITES:
        own_files = private[owner]
        orders = own_files[BATCHES[0]]['intake/opening/orders.csv']
        union, local, missing_by_batch = [], [], {}
        for idx, batch in enumerate(BATCHES):
            key = f'intake/{batch}/postings.csv'
            union.extend(private[s][batch][key] for s in SITES)
            local.append(own_files[batch][key])
            complete = reconcile(union, orders)
            isolated = reconcile(local, orders)
            if complete != truth[owner][idx]:
                raise ValueError(f'Incorrect reconstructed {owner}/{batch} ledger')
            missing = sorted(k for k in complete if isolated[k][:2] != complete[k][:2])
            if not missing:
                raise ValueError(f'{owner}/{batch} has no missing counterpart facts')
            missing_by_batch[batch] = len(missing)
        # Change one posting at each foreign depot in turn, leaving all owner inputs fixed.
        counterfactuals = {}
        for foreign in SITES:
            if foreign == owner:
                continue
            key = 'intake/returns_close/postings.csv'
            rows = read_csv(private[foreign][BATCHES[-1]][key], FACTS)
            selected = next(row for row in rows if row['order_id'] in complete)
            offset = -1 if selected['posting_type'] == 'adjustment' else 1
            selected['units'] = str(int(selected['units']) + offset)
            revised = csv_text(FACTS, ([row[c] for c in FACTS] for row in rows))
            other_world = [revised if (s, batch) == (foreign, BATCHES[-1])
                           else private[s][batch][f'intake/{batch}/postings.csv']
                           for batch in BATCHES for s in SITES]
            modified = reconcile(other_world, orders)
            changed = [k for k in complete if complete[k] != modified[k]]
            ticket = selected['order_id']
            if changed != [ticket] or abs(modified[ticket][0] - complete[ticket][0]) != 1:
                raise ValueError('Foreign counterfactual did not isolate one order quantity')
            counterfactuals[foreign] = {'counterfactual_order': ticket,
                                        'closing_net_change': modified[ticket][0] - complete[ticket][0]}
        summary[owner] = {'local_unresolved': missing_by_batch, 'all_batches_reconstructed': True,
                          **next(iter(counterfactuals.values())), 'by_foreign_depot': counterfactuals}
    return summary
