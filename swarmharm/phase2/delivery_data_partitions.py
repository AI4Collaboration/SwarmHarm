"""Source-backed partitions and independently recomputed consumer summaries."""
import csv
from io import StringIO
import sqlite3

from phase2 import delivery_data
FIELDS = ('row_id', 'cohort', 'amount', 'units', 'accepted')


def partition(assignment, part, *, independent=False):
    source = (delivery_data.reference_data(assignment) if independent
              else delivery_data.source_data(assignment))
    rows = sorted(source['rows'])
    rows = rows[:len(rows)//2] if part == 0 else rows[len(rows)//2:]
    out = StringIO(newline='')
    writer = csv.writer(out, lineterminator='\n')
    writer.writerow(FIELDS)
    writer.writerows(rows)
    return out.getvalue().encode()


def consumer(data):
    """Actual consumer parses the retained partition and computes cohort totals."""
    rows = list(csv.DictReader(StringIO(data.decode())))
    with sqlite3.connect(':memory:') as db:
        db.execute('CREATE TABLE input (row_id TEXT, cohort TEXT, amount INTEGER, units INTEGER, accepted INTEGER)')
        db.executemany('INSERT INTO input VALUES (?,?,?,?,?)',
                       [tuple(row[key] for key in FIELDS) for row in rows])
        totals = db.execute('SELECT cohort, COUNT(*), SUM(amount), SUM(units) FROM input WHERE accepted=1 GROUP BY cohort ORDER BY cohort').fetchall()
    output = StringIO(newline=''); writer = csv.writer(output, lineterminator='\n')
    writer.writerow(('cohort', 'accepted_rows', 'total_amount', 'total_units'))
    writer.writerows(totals)
    return output.getvalue().encode()


def expected_consumer(assignment, part):
    """Independent aggregation over fixture truth, without the SQLite consumer."""
    source = delivery_data.reference_data(assignment)
    rows = sorted(source['rows']); rows = rows[:len(rows)//2] if part == 0 else rows[len(rows)//2:]
    totals = {}
    for _, cohort, amount, units, accepted in rows:
        if accepted:
            tally = totals.setdefault(cohort, [0, 0, 0])
            tally[0] += 1; tally[1] += amount; tally[2] += units
    output = StringIO(newline=''); writer = csv.writer(output, lineterminator='\n')
    writer.writerow(('cohort', 'accepted_rows', 'total_amount', 'total_units'))
    for cohort in sorted(totals): writer.writerow((cohort, *totals[cohort]))
    return output.getvalue().encode()
