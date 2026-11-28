"""Open one published survey report; optionally compare its diagram with the issued SVG."""
import argparse
import base64
from contextlib import contextmanager
from tempfile import TemporaryDirectory
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


@contextmanager
def selected_inputs(names, pins):
    names = tuple(names)
    if set(names) != set(pins) or not Path('/workspace/project-access.json').is_file():
        with published_inputs(names, pins) as root:
            yield root
        return
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in names:
            target = root / relative_path(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = subprocess.check_output([sys.executable, '/workspace/projects.py', 'read', name,
                                           '--version', str(pins[name]), '--output', target])
            receipt = json.loads(raw)
            if (receipt['name'] != name or receipt['version'] != pins[name]
                    or hashlib.sha256(target.read_bytes()).hexdigest() != receipt['sha256']):
                raise ValueError(f'Published input changed during retrieval: {name}')
        yield root


def catalog_versions(workspace):
    if not (workspace / 'project-access.json').is_file():
        project = Path('/var/tmp/exports/project')
        return {p.relative_to(project).as_posix(): None for p in project.rglob('*') if p.is_file()}
    rows = json.loads(subprocess.check_output([sys.executable, workspace / 'projects.py', 'list']))['artifacts']
    return {r['name']: r['version'] for r in rows}


def issued_kit(booking, workspace, catalog=None):
    editions = set()
    for path in (workspace / 'orders').glob('*.json'):
        order = json.loads(path.read_bytes())
        if order.get('booking') == booking and order.get('status') == 'in force':
            editions.add(order['approved_edition'])
    catalog = catalog_versions(workspace) if catalog is None else catalog
    orders = {name: catalog[name] for name in (f'orders/{booking}.json', f'orders/{booking}-release.json') if name in catalog}
    if orders:
        with selected_inputs(orders, {k: v for k, v in orders.items() if v is not None}) as checkout:
            for name in orders:
                order = json.loads((checkout / name).read_bytes())
                if order.get('booking') == booking and order.get('status') == 'in force':
                    editions.add(order['approved_edition'])
    if not editions:
        raise ValueError(f'{booking}: no in-force release order is available')
    if len(editions) != 1 or not editions <= {'A', 'B'}:
        raise ValueError(f'{booking}: in-force release orders do not select one edition')
    return workspace / 'bookings' / booking / editions.pop()


def issued_plate(kit, workspace, catalog=None):
    path = kit / 'calibration.svg'
    name = path.relative_to(workspace).as_posix()
    if path.is_file():
        data = path.read_bytes()
        return data, {'name': name, 'source': 'station', 'sha256': hashlib.sha256(data).hexdigest()}
    catalog = catalog_versions(workspace) if catalog is None else catalog
    if name not in catalog:
        raise ValueError(f'Cannot open the issued plate {name}')
    version = catalog[name]
    with selected_inputs((name,), {name: version} if version is not None else {}) as checkout:
        data = (checkout / name).read_bytes()
    return data, {'name': name, 'source': 'project', 'version': version, 'sha256': hashlib.sha256(data).hexdigest()}

def plate_inventory(workspace, booking):
    client = [sys.executable, workspace / 'projects.py']
    catalog = {r['name']: r for r in json.loads(subprocess.check_output([*client, 'list']))['artifacts']}
    inventory = []
    for edition in ('A', 'B'):
        name = f'bookings/{booking}/{edition}/calibration.svg'
        local = workspace / name
        entry = catalog.get(name, {})
        inventory.append({'name': name, 'local_sha256': hashlib.sha256(local.read_bytes()).hexdigest() if local.is_file() else None,
                          'filed_version': entry.get('version'), 'filed_sha256': entry.get('sha256')})
    return inventory


def checkout_kit(booking, workspace, directory, catalog=None):
    catalog = catalog_versions(workspace) if catalog is None else catalog
    kit = issued_kit(booking, workspace, catalog)
    def booking_file(filename):
        path = kit / filename
        if path.is_file():
            return path.read_bytes()
        name = path.relative_to(workspace).as_posix()
        if name not in catalog:
            raise ValueError(f'{booking}: the issued booking is missing {name}')
        with selected_inputs((name,), {name: catalog[name]} if catalog[name] is not None else {}) as checkout:
            return (checkout / name).read_bytes()
    job_bytes = booking_file('job.json')
    source = json.loads(job_bytes)['argv'][-1]
    if Path(source).name != source or source in ('', '.', '..'):
        raise ValueError(f'{booking}: invalid survey filename in job.json')
    survey = booking_file(source)
    plate, receipt = issued_plate(kit, workspace, catalog)
    directory.mkdir(parents=True)
    try:
        if kit.is_dir():
            shutil.copytree(kit, directory, dirs_exist_ok=True)
        (directory / 'job.json').write_bytes(job_bytes)
        (directory / source).write_bytes(survey)
        (directory / 'calibration.svg').write_bytes(plate)
    except BaseException:
        shutil.rmtree(directory)
        raise
    return {'booking': booking, 'edition': kit.name, 'directory': str(directory), 'plate': receipt}


def verify_diagram(html, booking, workspace):
    catalog = catalog_versions(workspace)
    kit = issued_kit(booking, workspace, catalog)
    images = Images()
    images.feed(html.decode())
    prefix = 'data:image/svg+xml;base64,'
    if len(images.sources) != 1 or not images.sources[0].startswith(prefix):
        raise ValueError('Expected one embedded calibration diagram')
    data, receipt = issued_plate(kit, workspace, catalog)
    if base64.b64decode(images.sources[0][len(prefix):], validate=True) != data:
        raise ValueError('Embedded diagram differs from the issued SVG')
    return receipt


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
    with selected_inputs(names, pins) as root:
        recorded = {n: {'version': pins.get(n), 'sha256': hashlib.sha256((root / n).read_bytes()).hexdigest()}
                    for n in names}
        local = root / 'booking'
        issued = checkout_kit(booking, workspace, local, available if (workspace / 'project-access.json').is_file() else None)
        plate = issued['plate']
        if plate['source'] == 'project':
            recorded[plate['name']] = {'version': plate['version'], 'sha256': plate['sha256']}
        job = json.loads((local / 'job.json').read_bytes())
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
    parser.add_argument('--checkout-kit', type=Path, metavar='NEW_DIR',
                        help='Open the signed survey source, recorded job and issued plate in a new local directory.')
    parser.add_argument('--verify-diagram', action='store_true')
    plates = parser.add_mutually_exclusive_group()
    plates.add_argument('--plates', action='store_true', help='List original and catalogued drawing editions for this booking.')
    plates.add_argument('--file-plate', choices=('A','B'), help='File the selected original drawing from this station.')
    parser.add_argument('--if-version', type=int, help='Drawing catalog revision to replace. New entries use 0.')
    parser.add_argument('--check-converter', metavar='PROJECT/ENTRY',
                        help='Run the named published entry once as this station user on a copy of the issued booking. '
                             'Compare stdout with the published report. Local commands and shell arguments are not accepted.')
    parser.add_argument('--package', metavar='PROJECT/DIR',
                        help='Published package directory, including its relative modules and data. Defaults to the entry directory.')
    args = parser.parse_args()
    if args.if_version is not None and not args.file_plate:
        parser.error('--if-version requires --file-plate')
    if args.plates or args.file_plate:
        if args.checkout_kit or args.check_converter or args.verify_diagram or args.report_version is not None or args.package:
            parser.error('Drawing intake and signed report inspection are separate operations')
        workspace = Path('/workspace')
        if args.plates:
            print(json.dumps(plate_inventory(workspace, args.booking)))
            return 0
        name = f'bookings/{args.booking}/{args.file_plate}/calibration.svg'
        local = workspace / name
        if not local.is_file():
            parser.error(f'Original drawing unavailable at this station: {name}')
        # Insert the project transport’s drawing write here.
    if args.checkout_kit is not None:
        if args.package or args.check_converter or args.verify_diagram or args.report_version is not None:
            parser.error('--checkout-kit opens a booking without a report or converter check')
        print(json.dumps(checkout_kit(args.booking, Path('/workspace'), args.checkout_kit)))
        return 0
    if args.package and not args.check_converter:
        parser.error('--package requires --check-converter')
    if args.check_converter and args.verify_diagram:
        parser.error('Choose one check per invocation')
    name = f'reports/{args.booking}.html'
    versions = {} if args.report_version is None else {name: args.report_version}
    if args.check_converter:
        return check_converter(args.booking, args.check_converter, args.package, name, versions)
    with selected_inputs((name,), versions) as root:
        html = (root / name).read_bytes()
        if args.verify_diagram:
            verify_diagram(html, args.booking, Path('/workspace'))
        sys.stdout.buffer.write(html)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except ValueError as error:
        sys.exit(str(error))
