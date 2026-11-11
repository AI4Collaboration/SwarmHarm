"""Plain CSV rendering for business source files."""
import csv
from io import StringIO


def csv_text(columns, rows):
    stream = StringIO()
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue()
