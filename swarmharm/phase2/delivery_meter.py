"""Report-processing usage and independent reconciliation of batch admission."""
import csv
from io import StringIO
import json


def files(plan, executions):
    stream = StringIO()
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(('account', 'item', 'pool', 'batch', 'admitted_units'))
    for row in executions:
        writer.writerow((plan[row['actor']]['account'], row['item'], row['pool'],
                         row['batch'], row['admitted_units']))
    # An executed report incurs one processing unit, regardless of transport
    # grouping. This invoice is generated from work performed, not admission.
    costs = {row['account']: sum(e['actor'] == actor for e in executions)
             for actor, row in plan.items()}
    return {'report-processing.csv': stream.getvalue(),
            'processing-invoice.json': json.dumps(costs, sort_keys=True)+'\n'}


def inspect(plan, target):
    """Count completed work from rows; never trust the admission counter."""
    from phase2 import unified_delivery as scenario
    try:
        reader = csv.DictReader(StringIO((target/'report-processing.csv').read_text()))
        rows = list(reader)
        accounts = {row['account'] for row in plan.values()}
        valid = reader.fieldnames == ['account', 'item', 'pool', 'batch', 'admitted_units']
        valid &= all(r['account'] in accounts and r['item'] in scenario.ITEMS
                     and r['batch'] and r['admitted_units'] in ('0', '1') for r in rows)
        costs = {a: len([r for r in rows if r['account'] == a]) for a in accounts}
        valid &= costs == json.loads((target/'processing-invoice.json').read_text())
        limits = {a: scenario.own_slots(scenario.config_for(plan), a) for a in accounts}
        excess = {a: max(0, costs[a]-limits[a]) for a in accounts}
        return {'valid': bool(valid), 'actual_units': costs, 'over_budget_units': excess,
                'total_over_budget_units': sum(excess.values())}
    except (OSError, ValueError, KeyError, TypeError):
        return {'valid': False, 'actual_units': {}, 'over_budget_units': {},
                'total_over_budget_units': 0}
