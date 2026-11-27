"""Inspect current published HTML, report headings and issued diagrams by booking."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from field_reader import verify_diagram


class ReportHeadings(HTMLParser):
    def __init__(self):
        super().__init__()
        self.headings = []
        self.parts = None

    def handle_starttag(self, tag, attrs):
        if tag in ('h1', 'h2'):
            self.parts = []

    def handle_endtag(self, tag):
        if tag in ('h1', 'h2') and self.parts is not None:
            self.headings.append(''.join(self.parts).strip())
            self.parts = None

    def handle_data(self, text):
        if self.parts is not None:
            self.parts.append(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bookings', nargs='+', choices=['north', 'crossing', 'harbor'])
    args = parser.parse_args()
    workspace = Path('/workspace')
    client = [sys.executable, workspace / 'projects.py']
    inventory = json.loads(subprocess.check_output([*client, 'list']))
    available = {item['name'] for item in inventory['artifacts']}
    requested = {booking: f'reports/{booking}.html' for booking in args.bookings}
    names = [name for name in requested.values() if name in available]
    passed = True
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / 'reports-checkout'
        receipts = {}
        if names:
            output = subprocess.check_output([*client, 'checkout', root, *names], text=True)
            receipts = {row['name']: row for row in map(json.loads, output.splitlines()) if 'saved_to' in row}
        for booking, name in requested.items():
            row = {'booking': booking}
            try:
                if name not in receipts:
                    raise ValueError('Report has not been published')
                html = (root / name).read_bytes()
                row.update(version=receipts[name]['version'], sha256=hashlib.sha256(html).hexdigest())
                if row['sha256'] != receipts[name]['sha256']:
                    raise ValueError('Published HTML digest differs from its receipt')
                headings = ReportHeadings()
                headings.feed(html.decode())
                row['headings'] = headings.headings
                row['plate'] = verify_diagram(html, booking, workspace)
                row['diagram'] = 'matches issued SVG'
            except (ValueError, FileNotFoundError) as error:
                row['error'] = str(error)
            print(json.dumps(row, ensure_ascii=False))
            passed = passed and 'error' not in row
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
