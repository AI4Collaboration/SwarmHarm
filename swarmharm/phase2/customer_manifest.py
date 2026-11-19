"""October customer distribution from the close manifest and current released packs."""
import base64
import csv
from io import StringIO
from pathlib import Path

from phase2 import work_files

PATH = work_files.ROOT + '/october-distribution.csv'
COLUMNS = ['account', 'release_reference']


def opening_worksheet(accounts):
    sheet = StringIO(newline='')
    writer = csv.writer(sheet, lineterminator='\n')
    writer.writerow(COLUMNS)
    writer.writerows((account, '') for account in accounts)
    return sheet.getvalue()


def entries(shared):
    record = shared.get(PATH)
    if not record or record.get('deleted'):
        return {}
    try:
        text = base64.b64decode(record['data'], validate=True).decode('utf-8-sig')
        rows = csv.reader(StringIO(text, newline=''), strict=True)
        if next(rows, []) != COLUMNS:
            return {}
        result = {}
        for row in rows:
            if len(row) == 2 and all(row):
                result.setdefault(row[0], set()).add(row[1])
        return result
    except (ValueError, csv.Error):
        return {}


def delivery_files(plan, releases, shared):
    scheduled = entries(shared)
    files = {}
    for actor, release in releases.items():
        account = plan[actor]['account']
        if scheduled.get(account) == {release['reference']}:
            for name, contents in release['files'].items():
                files[f'customer-inboxes/{account}/{name}.csv'] = contents
    return files


def distribute(directory, plan, releases, shared):
    for relative, contents in delivery_files(plan, releases, shared).items():
        target = Path(directory) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding='utf-8')
