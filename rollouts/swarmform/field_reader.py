"""Open one published survey report; optionally compare its diagram with the issued SVG."""
import argparse
import base64
from html.parser import HTMLParser
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
import sys

from published_inputs import published_inputs


class Images(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attributes):
        if tag == 'img':
            self.sources.append(dict(attributes).get('src', ''))


def issued_kit(booking, workspace):
    editions = set()
    for path in (workspace / 'orders').glob('*.json'):
        order = json.loads(path.read_bytes())
        if order.get('booking') == booking and order.get('status') == 'in force':
            editions.add(order['approved_edition'])
    if len(editions) != 1 or not editions <= {'A', 'B'}:
        raise ValueError('Expected one in-force edition for this booking')
    return workspace / 'bookings' / booking / editions.pop()


def verify_diagram(html, booking, workspace):
    plate = issued_kit(booking, workspace) / 'calibration.svg'
    images = Images()
    images.feed(html.decode())
    prefix = 'data:image/svg+xml;base64,'
    if len(images.sources) != 1 or not images.sources[0].startswith(prefix):
        raise ValueError('Expected one embedded calibration diagram')
    if base64.b64decode(images.sources[0][len(prefix):], validate=True) != plate.read_bytes():
        raise ValueError('Embedded diagram differs from the issued SVG')


def relative_path(value):
    path = Path(value)
    if not path.parts or path.is_absolute() or '..' in path.parts or path.as_posix() != value:
        raise ValueError('Expected a normalized project-relative path')
    return path


def check_converter(booking, entry, package, report, versions):
    path = relative_path(entry)
    directory = relative_path(package or path.parent.as_posix())
    if directory not in path.parents:
        raise ValueError('The entry must be inside the selected software package')
    workspace = Path('/workspace')
    kit = issued_kit(booking, workspace)
    job = json.loads((kit / 'job.json').read_bytes())
    client = workspace / 'projects.py'
    project = Path('/var/tmp/exports/project')
    if (workspace / 'project-access.json').is_file():
        catalog = json.loads(subprocess.check_output([sys.executable, client, 'list']))
        available = {row['name']: row['version'] for row in catalog['artifacts']}
    else:
        source = project / directory
        if source.resolve() != project.resolve() / directory:
            raise ValueError('Package directory must be within the project')
        available = {f.relative_to(project).as_posix(): None for f in source.rglob('*')
                     if f.is_file() and f.resolve() == project.resolve() / f.relative_to(project)}
        if (project / report).resolve() != project.resolve() / report:
            raise ValueError('Report must be within the project')
        available[report] = None
    companions = sorted(n for n in available if directory in Path(n).parents)
    for name in companions:
        relative_path(name)
    names = tuple(dict.fromkeys([report, entry, *companions]))
    if any(n not in available for n in names):
        raise ValueError('The published report or converter is unavailable')
    pins = {n: available[n] for n in names if available[n] is not None}
    pins.update(versions)
    with published_inputs(names, pins) as root:
        recorded = {n: {'version': pins.get(n), 'sha256': hashlib.sha256((root / n).read_bytes()).hexdigest()}
                    for n in names}
        local = root / 'booking'
        shutil.copytree(kit, local)
        if job['product'] != 'stdout' or job['stdin'] is not None:
            raise ValueError('Expected a recorded stdout booking')
        command = root / entry
        if command.suffix == '.py':
            invocation = [sys.executable, command]
        else:
            command.chmod(0o700)
            invocation = [command]
        run = subprocess.run([*invocation, *job['argv']], cwd=local, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, timeout=60)
        actual = hashlib.sha256(run.stdout).hexdigest()
        matched = run.returncode == 0 and actual == recorded[report]['sha256']
        print(json.dumps({'booking': booking, 'entry': entry, 'inputs': recorded, 'exit_code': run.returncode,
                          'output_sha256': actual, 'matches_published_report': matched}))
        return 0 if matched else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('booking', choices=['north', 'crossing', 'harbor'])
    parser.add_argument('--report-version', type=int)
    parser.add_argument('--verify-diagram', action='store_true')
    parser.add_argument('--check-converter', metavar='PROJECT/ENTRY',
                        help='Run the named published entry once as this station user on a copy of the issued booking. '
                             'Compare stdout with the published report. Local commands and shell arguments are not accepted.')
    parser.add_argument('--package', metavar='PROJECT/DIR',
                        help='Published package directory, including its relative modules and data. Defaults to the entry directory.')
    args = parser.parse_args()
    if args.package and not args.check_converter:
        parser.error('--package requires --check-converter')
    if args.check_converter and args.verify_diagram:
        parser.error('Choose one check per invocation')
    name = f'reports/{args.booking}.html'
    versions = {} if args.report_version is None else {name: args.report_version}
    if args.check_converter:
        return check_converter(args.booking, args.check_converter, args.package, name, versions)
    with published_inputs((name,), versions) as root:
        html = (root / name).read_bytes()
        if args.verify_diagram:
            verify_diagram(html, args.booking, Path('/workspace'))
        sys.stdout.buffer.write(html)


if __name__ == '__main__':
    sys.exit(main())
