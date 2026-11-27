"""File firmware diagnostics, inspect a scan, or issue an edition under a local release order."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from xml.etree.ElementTree import ParseError

from diagnostic_records import read_xml

WORKSPACE = Path('/workspace')
BOOKINGS = ('north', 'crossing', 'harbor')
EDITIONS = ('A', 'B')


def project(*arguments):
    cmd = [sys.executable, str(WORKSPACE / 'projects.py'), *map(str, arguments)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode:
        raise ValueError(result.stderr.strip() or 'Project operation failed')
    return json.loads(result.stdout)


def write(name, source, version):
    config = json.loads((WORKSPACE / 'project-access.json').read_text())
    if config['interface'] == 'socket':
        from socket_worktree import MAX_OBJECT, request
        with source.open('rb') as stream:
            data = stream.read(MAX_OBJECT + 1)
        if len(data) > MAX_OBJECT:
            raise ValueError('Scan exceeds the project service limit')
        return request(config, 'write', name=name, data=base64.b64encode(data).decode(),
                       base_version=version)
    return project('write', name, source, '--if-version', version)


def intake(booking, edition):
    return f'diagnostics/intake/{booking}/{edition}.xml'


def scan(name, version):
    record = project('read', name, '--version', version)
    xml = record['text'].encode()
    if len(xml) != record['bytes'] or hashlib.sha256(xml).hexdigest() != record['sha256']:
        raise ValueError('The stored XML does not match its revision')
    read_xml(record['text'])
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for verb,help_text in [('file','Archive a local XML scan for a firmware edition.'),
                           ('show','Display an exact edition scan.'),
                           ('issue','Issue the chosen scan under the release orders on this desk.'),
                           ('status','Inspect the issued XML and matching filed editions.')]:
        command = sub.add_parser(verb, help=help_text)
        command.add_argument('booking', choices=BOOKINGS)
        if verb != 'status':
            command.add_argument('edition', choices=EDITIONS)
        if verb == 'file':
            command.add_argument('report', type=Path)
        elif verb in ('show', 'issue'):
            command.add_argument('version', type=int)
    args = parser.parse_args()
    released = f'diagnostics/{args.booking}.xml'
    if args.action == 'show':
        print(json.dumps(scan(intake(args.booking, args.edition), args.version)))
        return
    listing = {r['name']:r for r in project('list')['artifacts']}
    if args.action == 'status':
        filed = {ed:listing[intake(args.booking, ed)] for ed in EDITIONS if intake(args.booking, ed) in listing}
        current = scan(released, listing[released]['version']) if released in listing else None
        match = [ed for ed, record in filed.items() if current and record['sha256'] == current['sha256']]
        print(json.dumps({**(current or {'name': released, 'version': None}), 'filed': filed, 'matching_editions': match}))
        return
    name = intake(args.booking, args.edition)
    if args.action == 'file':
        checkout = WORKSPACE/'bookings'/args.booking/args.edition
        if not (checkout/'meter.c').is_file() or not (checkout/'job.json').is_file():
            raise ValueError('This desk does not hold the indicated firmware edition')
        read_xml(args.report.read_text())
        print(json.dumps(write(name, args.report, listing.get(name,{}).get('version',0))))
        return
    orders = (json.loads(p.read_text()) for p in (WORKSPACE/'orders').glob('*.json'))
    approved = {o['approved_edition'] for o in orders if o['booking'] == args.booking and o['status'] == 'in force'}
    if approved != {args.edition}:
        raise ValueError('This desk has no unambiguous in-force order for the requested edition')
    chosen = scan(name, args.version)
    with TemporaryDirectory() as directory:
        report = Path(directory)/'issued.xml'
        report.write_bytes(chosen['text'].encode())
        print(json.dumps(write(released, report, listing.get(released,{}).get('version',0))))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, ParseError, RuntimeError) as error:
        sys.exit(str(error))
