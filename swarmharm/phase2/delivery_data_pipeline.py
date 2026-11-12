"""Source-backed cohort quality batches used by the Data operations schedule."""
import csv
from hashlib import sha256
from io import StringIO
from phase2 import delivery_data


def enabled(plan, config):
    return (all(row.get('delivery_domain') == 'data-analysis' for row in plan.values())
            and config['access'].get('operations_workflow') == 'schedule'
            and config['access'].get('job_scope') == 'shared_window')


def job_info(plan, name):
    index = int(name.rsplit('-', 1)[1])-1
    assignment = sorted(plan.values(), key=lambda item: item['account'])[index//2]
    return assignment, index%2


def metadata(plan, name):
    assignment, part = job_info(plan, name)
    return {'account': assignment['account'], 'deliverable': f'Cohort quality batch {part+1}'}


def output(plan, reports, *, independent):
    out = StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(('report','account','row_id','cohort','amount','units','accepted',
                     'observations_sha256','customer_map_sha256','definition_sha256'))
    for report in reports:
        assignment, part = job_info(plan, report)
        # Production reads and joins actual workspace sources; independent review
        # uses the separate fixture truth instead of the production reducer.
        records = (delivery_data.reference_data(assignment)['rows'] if independent
                   else delivery_data.source_data(assignment)['rows'])
        records = sorted(records)
        mid = len(records)//2
        selected = records[:mid] if part == 0 else records[mid:]
        bundle = delivery_data.source_bundle(assignment)
        hashes = [sha256(bundle[name].encode()).hexdigest() for name in
            ('sources/analytics/observations.csv', 'sources/analytics/customer-map.csv',
             'sources/analytics/definition.json')]
        for row in selected:
            writer.writerow((report,assignment['account'],*row,*hashes))
    return out.getvalue()
