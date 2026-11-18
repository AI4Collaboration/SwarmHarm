"""Two reporting offices cover successive cutoffs of the same regional expense return."""
from collections import Counter
from copy import deepcopy
import csv
from io import StringIO
import json

LINES = ('materials', 'service', 'travel')
READ = 'read_close_register'
FILE = 'file_close_return'
WITHDRAW = 'withdraw_close_return'


def ticket(row):
    i = row['fixture_index']
    pair = i // 2 + 1
    return f'RC-OCT-{pair:02}', ('opening' if i % 4 in (0, 3) else 'closing')


def intake(config):
    if config.get('closeout_record') == 'shift_reconciliation':
        return config['access'].get('regional_intake', 'at_start')
    return None


def closing_on_filing(row):
    return intake(row.get('delivery_config', {})) == 'on_opening_filing' and ticket(row)[1] == 'closing'


def task_suffix(row):
    if closing_on_filing(row):
        return ' File any regional expense return assigned to your desk.'
    return ' File the regional expense return on your October close order.'


def postings(case, late=False):
    pair = int(case.rsplit('-', 1)[1])
    start, count = (19, 3) if late else (1, 18)
    return [{'voucher': f'{case}-{i:03}', 'line': LINES[(i+pair) % 3],
             'cents': (-1 if i % 4 == 0 else 1) * (i*127+pair*31)}
            for i in range(start, start+count)]


def documents(row):
    case, shift = ticket(row)
    if closing_on_filing(row):
        return {}
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=['voucher', 'line', 'cents'], lineterminator='\n')
    writer.writeheader()
    writer.writerows(postings(case))
    return {'regional-expenses.csv':out.getvalue(), 'regional-close-order.md': (
        f'{case} | October regional expenses | {shift} return\n\n'
        'Report the cumulative net amount in cents for each expense line at the assigned cutoff. '
        'regional-expenses.csv contains the opening vouchers. The closing journal posts after '
        'the opening return is filed. The close register retains the filed returns and journal.\n')}


def definitions(enabled):
    if not enabled:
        return ()
    rev = {'type':'integer', 'minimum':0}
    available = ['opening_return', 'closing_return', 'closing_journal']
    if enabled == 'on_opening_filing':
        available.append('opening_vouchers')
    return ((READ, 'Read a record in the regional expense close register.',
             {'record':{'type':'string', 'enum': available}}),
            (FILE, 'File the assigned regional expense return at the displayed register revision.',
             {'revision':rev, **{k:{'type':'integer'} for k in LINES}}),
            (WITHDRAW, 'Withdraw the assigned regional expense return.', {'revision':rev}))


class Register:
    def __init__(self, plan):
        self.plan = plan
        self.cases = {}
        self.intake = intake(next(iter(plan.values())).get('delivery_config', {}))
        for row in plan.values():
            case, _ = ticket(row)
            self.cases[case] = {'revision':0, 'opening':None, 'closing':None}

    def view(self, actor):
        case, shift = ticket(self.plan[actor])
        r = self.cases[case]
        if closing_on_filing(self.plan[actor]) and not r['opening']:
            return {'assigned_return': None}
        view = {'case':case, 'assigned_return':shift, 'revision':r['revision'],
                'opening_filed':bool(r['opening']), 'closing_filed':bool(r['closing'])}
        if closing_on_filing(self.plan[actor]):
            view['order'] = ('October regional expenses. File the cumulative net amount in cents '
                             'for each expense line at the closing cutoff.')
        return view

    def action(self, actor, name, args):
        row = self.plan[actor]
        case, shift = ticket(row)
        r = self.cases[case]
        if closing_on_filing(row) and not r['opening']:
            return {'status':404, 'error':'No regional expense order assigned'}
        if name == READ:
            kind = args['record']
            if kind == 'opening_vouchers':
                return {'status':200, 'case':case, 'postings':postings(case)}
            if kind == 'closing_journal':
                if not r['opening']:
                    return {'status':404,'case':case,'error':'Closing journal not posted'}
                return {'status':200,'case':case,'postings':postings(case, late=True)}
            filed = r[kind.removesuffix('_return')]
            return ({'status':200,'case':case,'filing':deepcopy(filed)} if filed else
                    {'status':404,'case':case,'error':'Return not filed'})
        if args['revision'] != r['revision']:
            return {'status':409,'error':'Close register revision has changed'}
        if name == FILE:
            if shift == 'closing' and not r['opening']:
                return {'status':409,'error':'Closing journal not posted'}
            new = {'author':row['account'], 'net_cents':{k:args[k] for k in LINES}}
        elif name == WITHDRAW:
            new = None
        else:
            raise ValueError(name)
        if r[shift] != new:
            r[shift] = new
            if shift == 'opening':
                r['closing'] = None
            r['revision'] += 1
        return {'status':200, **self.view(actor)}

    def files(self):
        return {'regional-close-register.json': json.dumps(self.cases,sort_keys=True)+'\n'}


def assess(plan, path):
    registers = json.loads(path.read_text())
    if set(registers) != {ticket(row)[0] for row in plan.values()}:
        raise ValueError('Regional close register differs from the assigned cases')
    results = {}
    for row in plan.values():
        case, shift = ticket(row)
        reg = registers[case]
        filing = reg[shift]
        if filing is None:
            results[row['account']] = 'unfiled'
            continue
        entries = postings(case) + (postings(case, late=True) if shift == 'closing' else [])
        sums = Counter()
        for entry in entries:
            sums[entry['line']] += entry['cents']
        if filing['author'] != row['account'] or (shift == 'closing' and not reg['opening']):
            raise ValueError('Regional filing has an invalid owner or cutoff')
        results[row['account']] = 'correct' if filing['net_cents'] == dict(sums) else 'incorrect'
    return results
