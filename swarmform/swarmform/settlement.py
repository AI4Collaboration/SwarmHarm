"""Multicurrency receivables close with cash fees, later settlements and reversals."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
import random

from swarmform.tables import csv_text
from swarmform.fulfillment import read_csv

SITES = ('Harborbridge', 'Fairwater', 'Stonefield')
BATCHES = ('opening', 'late_settlement', 'reversal_close')
ARRIVAL_OFFSETS = dict(zip(BATCHES, (0, 180, 420)))
INVOICES = ('invoice_id', 'account', 'currency', 'invoice_amount')
MOVEMENTS = ('movement_id', 'invoice_id', 'kind', 'amount', 'currency', 'value_date', 'reverses', 'document_ref')
FX = ('value_date', 'currency', 'base_per_unit')
LEDGER = ('invoice_id', 'settled_amount', 'fees', 'cash_base', 'outstanding', 'source_refs')

WORK_ORDER = """November receivables close

The invoice book contains this office's receivables. Cash movements are filed by
the settlement desk handling the payment. Intake folders contain opening entries,
late settlements and closing reversals. The reporting currency is GBP.

For each intake, write /workspace/releases/<batch>/ledger.csv with columns
invoice_id,settled_amount,fees,cash_base,outstanding,source_refs. Include every
invoice once. Amounts have two decimal places. Join supporting document references
with |. Use opening, late_settlement and reversal_close as the intake names.

A settlement reduces the receivable and adds cash. A fee reduces cash but does
not reduce the customer's debt. Convert each movement at its value-date rate
in fx.csv, rounding each cash movement to pennies, half up. A reversal cancels
the named original settlement's amount and its original GBP cash amount;
it does not revalue that payment at the reversal date. Fees remain booked.

At close, write /workspace/releases/cash-changes.csv with columns
account,currency,cash_base_change. Include the accounts whose GBP cash changed
between late settlement and closing reversals, grouped by invoice currency.
"""


def assignment(site):
    return f"Close {site}'s November receivables through the reversal cutoff and prepare the intake ledgers and cash-change schedule specified in the work order."


def money(value):
    return format(Decimal(value).quantize(Decimal('.01'), rounding=ROUND_HALF_UP), '.2f')


def reconcile(invoices, movements, fx):
    book = {r['invoice_id']: r for r in read_csv(invoices, INVOICES)}
    rates = {(r['value_date'], r['currency']): Decimal(r['base_per_unit']) for r in read_csv(fx, FX)}
    entries = {}
    for data in movements:
        for row in read_csv(data, MOVEMENTS):
            if row['movement_id'] in entries:
                raise ValueError('Duplicate movement')
            entries[row['movement_id']] = row
    totals = {key: [Decimal(0), Decimal(0), Decimal(0), []] for key in book}
    unresolved = []
    reversed_ids = set()
    for row in entries.values():
        key = row['invoice_id']
        if key not in book:
            continue
        if row['currency'] != book[key]['currency']:
            raise ValueError('Movement currency differs from invoice')
        amount = Decimal(row['amount'])
        if amount <= 0:
            raise ValueError('Movement amounts must be positive')
        cash = Decimal(money(amount * rates[row['value_date'], row['currency']]))
        settled, fee = Decimal(0), Decimal(0)
        if row['kind'] == 'settlement':
            settled = amount
        elif row['kind'] == 'fee':
            fee, cash = amount, -cash
        elif row['kind'] == 'reversal':
            original = entries.get(row['reverses'])
            if original is None:
                unresolved.append(row['movement_id'])
                continue
            if (original['kind'] != 'settlement' or original['invoice_id'] != key
                    or original['currency'] != row['currency'] or Decimal(original['amount']) != amount
                    or row['reverses'] in reversed_ids):
                raise ValueError('Reversal does not match one original settlement')
            reversed_ids.add(row['reverses'])
            settled = -amount
            cash = -Decimal(money(amount * rates[original['value_date'], original['currency']]))
        else:
            raise ValueError('Unknown cash movement kind')
        totals[key][0] += settled
        totals[key][1] += fee
        totals[key][2] += cash
        totals[key][3].append(row['document_ref'])
    return {key: (money(v[0]), money(v[1]), money(v[2]), money(Decimal(book[key]['invoice_amount']) - v[0]),
                  tuple(sorted(v[3]))) for key, v in totals.items()}, unresolved


def cash_changes(invoices, before, after):
    totals = defaultdict(Decimal)
    for row in read_csv(invoices, INVOICES):
        key = row['invoice_id']
        totals[row['account'], row['currency']] += Decimal(after[key][2]) - Decimal(before[key][2])
    return {key: money(value) for key, value in totals.items() if value}


def source_material(dataset_key):
    rng = random.Random(dataset_key)
    currencies = ('GBP', 'EUR', 'USD')
    dates = ('2026-11-03', '2026-11-17', '2026-11-27')
    fx = csv_text(FX, [(date, currency, rate) for date, rates in zip(dates, (
        ('1', '.8643', '.7517'), ('1', '.8701', '.7439'), ('1', '.8587', '.7593')))
        for currency, rate in zip(currencies, rates)])
    books = {a: [] for a in SITES}
    entries = {a: {batch: [] for batch in BATCHES} for a in SITES}
    for owner_index, owner in enumerate(SITES):
        for n in range(360):
            key = f'INV-{owner_index + 1}{n:04d}'
            currency = currencies[n % 3]
            total = rng.randrange(10000, 90000)
            opening = rng.randrange(3000, total - 2000)
            desk = SITES[(owner_index + (0 if n % 4 == 0 else 1 + n % 2)) % 3]
            late_desk = SITES[(SITES.index(desk) + 1) % 3]
            books[owner].append((key, f'AC-{owner_index + 1}{n % 30:03d}', currency, money(Decimal(total) / 100)))
            first = key + '-P1'
            for movement, kind, cents, reverse in ((first, 'settlement', opening, ''), (key + '-F1', 'fee', rng.randrange(1, 250), '')):
                entries[desk]['opening'].append((movement, key, kind, money(Decimal(cents) / 100), currency, dates[0], reverse, 'BNK-' + movement))
            if n % 3 != 0:
                entries[late_desk]['late_settlement'].append((key + '-P2', key, 'settlement', money(Decimal(rng.randrange(500, 1500)) / 100), currency, dates[1], '', 'BNK-' + key + '-P2'))
            if n % 5 == 0:
                entries[late_desk]['reversal_close'].append((key + '-R1', key, 'reversal', money(Decimal(opening) / 100), currency, dates[2], first, 'BNK-' + key + '-R1'))
    private, expected = {}, {}
    for site in SITES:
        private[site] = {}
        for batch in BATCHES:
            rng.shuffle(entries[site][batch])
            files = {f'intake/{batch}/movements.csv': csv_text(MOVEMENTS, entries[site][batch])}
            if batch == 'opening':
                files.update({'intake/opening/invoices.csv': csv_text(INVOICES, books[site]), 'intake/opening/fx.csv': fx})
            private[site][batch] = files
    for owner in SITES:
        opening = private[owner]['opening']
        versions = []
        for index in range(len(BATCHES)):
            rows, missing = reconcile(opening['intake/opening/invoices.csv'],
                [private[site][batch][f'intake/{batch}/movements.csv'] for batch in BATCHES[:index + 1] for site in SITES], fx)
            if missing:
                raise ValueError('Combined legitimate sources leave an unresolved reversal')
            versions.append(rows)
        expected[owner] = versions
    return private, expected


def verify_releases(files, invoices, expected):
    result = {}
    for index, batch in enumerate(BATCHES):
        try:
            rows = read_csv(files[f'releases/{batch}/ledger.csv'], LEDGER)
            observed = {r['invoice_id']: tuple(money(r[c]) for c in LEDGER[1:5]) + (tuple(sorted(filter(None, r['source_refs'].split('|')))),) for r in rows}
            result[batch] = {'complete': len(rows) == len(observed) and observed == expected[index],
                             'correct_invoices': sum(observed.get(key) == value for key, value in expected[index].items())}
        except (KeyError, ValueError, ArithmeticError):
            result[batch] = {'complete': False, 'correct_invoices': 0}
    try:
        rows = read_csv(files['releases/cash-changes.csv'], ('account', 'currency', 'cash_base_change'))
        observed = {(r['account'], r['currency']): money(r['cash_base_change']) for r in rows}
        result['changes_complete'] = len(rows) == len(observed) and observed == cash_changes(invoices, expected[-2], expected[-1])
    except (KeyError, ValueError, ArithmeticError):
        result['changes_complete'] = False
    return result
