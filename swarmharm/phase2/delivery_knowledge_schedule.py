"""Source-backed Operations reports for the editorial processing schedule."""
import csv
from io import StringIO
from phase2 import delivery_data, delivery_retention


def enabled(plan, config):
    return (all(row.get('delivery_domain') == 'knowledge-work' for row in plan.values())
            and config.get('access', {}).get('operations_workflow') == 'schedule'
            and config.get('access', {}).get('job_scope') == 'shared_window'
            and config.get('access', {}).get('retention_store', 'disabled') == 'disabled')


def metadata(plan, name):
    assignment, part = delivery_retention.knowledge_assignment(plan, name)
    return {'account': assignment['account'], 'deliverable': f'Customer commitment review {part+1}',
            'due': 'October close'}


def output(plan, reports, *, independent):
    out = StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(('report', 'topic', 'editorial_summary'))
    for name in reports:
        assignment, part = delivery_retention.knowledge_assignment(plan, name)
        if independent:
            rows = sorted(delivery_data.reference_data(assignment)['rows'])
        else:
            detail = csv.DictReader(StringIO(delivery_data.render(assignment, 'detail')))
            rows = [[row[key] for key in ('commitment','project','due_day','completed_day','evidence')]
                    for row in detail]
        midpoint = len(rows)//2
        selected = rows[:midpoint] if part == 0 else rows[midpoint:]
        writer.writerow((name, delivery_retention.knowledge_label(plan, name),
                         delivery_retention.knowledge_text(selected, assignment)))
    return out.getvalue()
