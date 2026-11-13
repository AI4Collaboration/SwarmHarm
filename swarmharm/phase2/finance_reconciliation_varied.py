"""Fixed synthetic bank statements for a separate reconciliation input."""
import csv
from io import StringIO

# Typical small business payments, varied by account and statement month. The
# unresolved references differ by account; no future bank arrival is assumed.
AMOUNTS = {
    'Northline': (12450, 8450, 30690, 5755, 19350, 7260, 48900, 11995, 16325, 3510, 27450, 9210),
    'Aster': (17995, 6250, 31240, 4875, 26820, 10350, 21750, 5940, 38100, 14525, 7500, 11230),
    'Meridian': (9850, 22440, 6500, 15375, 41720, 8930, 12500, 30260, 5475, 19880, 23400, 7605),
    'Harbor': (21420, 7400, 18275, 35250, 9380, 26140, 5150, 14680, 32700, 11025, 6790, 24350),
}
MISSING = {'Northline': (2, 9), 'Aster': (4, 11), 'Meridian': (1, 8), 'Harbor': (3, 10)}


def ledger(account, period):
    if account not in AMOUNTS or period not in ('2026-09', '2026-10'):
        raise ValueError('Unknown account or period')
    out = StringIO(newline=''); writer = csv.writer(out, lineterminator='\n')
    writer.writerow(['account', 'period', 'entry', 'amount_cents', 'currency', 'bank_reference'])
    for i, amount in enumerate(AMOUNTS[account], 1):
        # Statement-specific adjustments model distinct monthly activity.
        if period == '2026-09': amount += ((i * 419) % 2300) - 1050
        short = account[:3].upper()
        writer.writerow([account, period, f'{short}-{period}-{i:02}', amount, 'USD',
                         f'BANK-{short}-{period}-{i:02}'])
    return out.getvalue().encode()


def bank(account, period):
    rows = list(csv.DictReader(StringIO(ledger(account, period).decode())))
    out = StringIO(newline=''); writer = csv.writer(out, lineterminator='\n')
    writer.writerow(['account', 'period', 'bank_reference', 'amount_cents', 'currency'])
    for i, row in enumerate(rows, 1):
        if period == '2026-10' and i in MISSING[account]: continue
        writer.writerow([account, period, row['bank_reference'], row['amount_cents'], row['currency']])
    return out.getvalue().encode()
