"""Open, file, and replay the survey archive's text-filter proofs."""
import argparse
import hashlib
import os
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PROJECT = Path('/workspace/projects.py')
REFERENCE = ['/opt/programbench/invoke', 'jgm__pandoc.5caad90']
READERS = ('markdown', 'rst')
WRITERS = ('html5', 'json', 'plain')
LAYOUT_FLAGS = ('--standalone','--embed-resources','--toc','--number-sections')


def project(*args):
    return json.loads(subprocess.check_output([sys.executable, PROJECT, *args]))


def booking_input(booking, edition):
    kit = Path('/workspace/bookings') / booking / edition
    filename = 'survey.rst' if booking == 'crossing' else 'survey.md'
    files = {}
    hashes = {}
    for name in ('job.json', filename, 'calibration.svg'):
        path = kit / name
        if not path.is_file():
            raise ValueError(f'Incomplete booking kit: {path}')
        raw = path.read_bytes()
        files[name] = raw.decode('utf-8')
        hashes[name] = hashlib.sha256(raw).hexdigest()
    return {'booking': booking, 'edition': edition, 'files': files, 'sha256': hashes,
            'reference_program': REFERENCE[1]}


def existing_booking(key, selected, version):
    item = project('read', key, '--version', str(version))
    body = item['text']
    if hashlib.sha256(body.encode()).hexdigest() != item['sha256']:
        raise ValueError(f'{key} v{version} digest mismatch')
    stored = json.loads(body)
    if ('reference' not in stored or
            {k: v for k, v in stored.items() if k not in ('reference', 'checked')} != selected):
        raise ValueError(f'{key} v{version} contains a different proof')
    print(body, end='')


def execute(program, proof, folder, timeout=60):
    if 'booking' in proof:
        booking = proof['booking']
        if booking not in ('north', 'crossing', 'harbor') or proof['edition'] not in ('A', 'B'):
            raise ValueError('Unknown booking kit')
        reader, filename = ('rst', 'survey.rst') if booking == 'crossing' else ('markdown', 'survey.md')
        files = proof['files']
        if set(files) != {'job.json', filename, 'calibration.svg'}:
            raise ValueError('Incomplete booking proof')
        for name, text in files.items():
            raw = text.encode('utf-8')
            if hashlib.sha256(raw).hexdigest() != proof['sha256'][name]:
                raise ValueError(f'Booking input differs from the recorded digest: {name}')
            (Path(folder) / name).write_bytes(raw)
        job = json.loads(files['job.json'])
        argv = job['argv']
        prefix = ['-f', reader, '-t', 'html5', '--wrap=none', '--standalone', '--embed-resources', '--metadata']
        if (job.get('stdin') is not None or job['product'] != 'stdout' or len(argv) != len(prefix) + 2
                or argv[:-2] != prefix or not argv[-2].startswith('pagetitle=') or argv[-1] != filename):
            raise ValueError('Unrecognized recorded survey job')
        run = subprocess.run([*program, *argv], stdin=subprocess.DEVNULL, capture_output=True,
                             cwd=folder, timeout=timeout)
        return dict(exit_code=run.returncode, stdout=run.stdout.decode('utf-8'), stderr=run.stderr.decode('utf-8'))

    reader, writer = proof['reader'], proof['writer']
    if reader not in READERS or writer not in WRITERS:
        raise ValueError('Unknown archive text filter')
    layout = proof.get('layout', [])
    if any(flag not in LAYOUT_FLAGS for flag in layout):
        raise ValueError('Unknown recorded layout option')
    if 'calibration.svg' in proof:
        (Path(folder) / 'calibration.svg').write_text(proof['calibration.svg'], encoding='utf-8')
    run = subprocess.run([*program, '-f', reader, '-t', writer, '--wrap=none', *layout],
                         input=proof['source'], text=True, capture_output=True, cwd=folder, timeout=32)
    return dict(exit_code=run.returncode, stdout=run.stdout, stderr=run.stderr)


def publish_booking(key, proof, slot):
    attempt = subprocess.run([sys.executable, PROJECT, 'write', key, slot, '--if-version', '0'],
                             capture_output=True)
    if not attempt.returncode:
        sys.stdout.buffer.write(attempt.stdout)
        return
    if f'{key}: expected version 0, current version ' not in attempt.stderr.decode(errors='replace'):
        sys.stderr.buffer.write(attempt.stderr)
        raise SystemExit(attempt.returncode)
    saved = project('read', key)
    existing = json.loads(saved['text'])
    if {k: v for k, v in existing.items() if k != 'checked'} != proof:
        raise ValueError(f"{key} v{saved['version']} contains a different proof")
    print(saved['text'], end='')
    return


JOB_ROOT = Path('/tmp/pandoc-proof-jobs')


def process_identity(pid):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[19] if fields[0] != 'Z' else None
    except FileNotFoundError:
        return None


def work(directory):
    proof = json.loads((directory / 'input.json').read_bytes())
    proof['reference'] = execute(REFERENCE, proof, directory, timeout=None)
    pending = directory / 'proof.tmp'
    pending.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + '\n')
    pending.replace(directory / 'proof.json')


def start_job(booking, edition):
    proof = booking_input(booking, edition)
    JOB_ROOT.mkdir(mode=0o700, exist_ok=True)
    directory = Path(tempfile.mkdtemp(dir=JOB_ROOT, prefix='job-'))
    (directory / 'input.json').write_text(json.dumps(proof, ensure_ascii=False))
    with (directory / 'worker.log').open('wb') as log:
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_run', directory.name],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    (directory / 'process.json').write_text(json.dumps([child.pid, process_identity(child.pid)]))
    print(directory.name)


def local_job(job):
    if not re.fullmatch(r'job-[a-zA-Z0-9_-]+', job):
        raise ValueError('Invalid local job identifier')
    directory = JOB_ROOT / job
    if not (directory / 'process.json').is_file():
        raise ValueError('Unknown local booking job')
    pid, identity = json.loads((directory / 'process.json').read_bytes())
    if (directory / 'proof.json').is_file():
        return directory, 'finished'
    return directory, 'running' if identity is not None and identity == process_identity(pid) else 'interrupted'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='action',required=True)
    start = subs.add_parser('start', help='Run the original booking job in a private station directory.')
    start.add_argument('--booking', choices=('north', 'crossing', 'harbor'), required=True)
    start.add_argument('--edition', choices=('A', 'B'), required=True)
    subs.add_parser('status', help='Inspect a local booking job.').add_argument('job')
    collect = subs.add_parser('collect', help='File the completed original booking proof under the selected archive name.')
    collect.add_argument('job')
    collect.add_argument('name')
    for op in ('show','record','check'):
        cmd = subs.add_parser(op)
        cmd.add_argument('name', help='Archive proof name')
        if op == 'record':
            cmd.add_argument('--booking', choices=('north', 'crossing', 'harbor'))
            cmd.add_argument('--edition', choices=('A', 'B'))
            cmd.add_argument('-f', choices=READERS)
            cmd.add_argument('-t', choices=WRITERS)
            cmd.add_argument('--plate', type=Path, help='Include this source drawing as calibration.svg in the proof.')
            for flag in LAYOUT_FLAGS:
                cmd.add_argument(flag, action='store_true')
        if op == 'check':
            cmd.add_argument('converter', type=Path, help='Local executable or Python entry')
            cmd.add_argument('--file',action='store_true',help='File this converter result with the proof')
    args = parser.parse_args()
    if args.action == 'start':
        start_job(args.booking, args.edition)
        return
    if args.action in ('status', 'collect'):
        directory, status = local_job(args.job)
        if args.action == 'status':
            print(json.dumps({'job': args.job, 'status': status}))
            return
        if status != 'finished':
            print(status, file=sys.stderr)
            raise SystemExit(75 if status == 'running' else 1)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', args.name):
        parser.error('Expected a proof name')
    key = 'archive/proofs/' + args.name + '.json'
    if args.action == 'collect':
        slot = directory / 'proof.json'
        publish_booking(key, json.loads(slot.read_bytes()), slot)
        return
    with tempfile.TemporaryDirectory() as folder:
        slot = Path(folder)/'proof.json'
        if args.action == 'record':

            layout = [flag for flag in LAYOUT_FLAGS if getattr(args, flag[2:].replace('-','_'))]
            if args.booking or args.edition:
                if not (args.booking and args.edition) or args.f or args.t or layout or args.plate:
                    parser.error('Select both --booking and --edition for an original booking job')
                proof = booking_input(args.booking, args.edition)
                from formation_store import mapped_request
                catalog = mapped_request({'operation': 'list'})['artifacts']
                version = next((row['version'] for row in catalog if row['name'] == key), None)
                if version is not None:
                    existing_booking(key, proof, version)
                    return
            else:
                if not (args.f and args.t):
                    parser.error('A text-filter proof requires -f and -t')
                proof = dict(reader=args.f, writer=args.t, source=sys.stdin.read())
                if layout:
                    proof['layout'] = layout
                if args.plate:
                    proof['calibration.svg'] = args.plate.read_bytes().decode('utf-8')
            proof['reference'] = execute(REFERENCE, proof, folder)
            version = 0
        else:
            item = project('read', key)
            version = item['version']
            proof = json.loads(item['text'])
        if args.action == 'show':
            print(json.dumps(proof,ensure_ascii=False,indent=2))
            return
        if args.action == 'check':
            entry = args.converter.resolve()
            program = [sys.executable,str(entry)] if entry.suffix == '.py' else [str(entry)]
            result = execute(program, proof, folder)
            reference = proof['reference']
            print(json.dumps({'source':proof.get('source', proof.get('files')),'reference':reference,'previous':proof.get('checked'),
                              'actual':result,'match':result==reference},ensure_ascii=False))
            if not args.file or proof.get('checked') == result:
                return
            proof['checked'] = result
        slot.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
        if args.action == 'record' and 'booking' in proof:
            publish_booking(key, proof, slot)
            return
        print(json.dumps(project('write',key,slot,'--if-version',str(version))))


if __name__ == '__main__':
    try:
        if sys.argv[1:2] == ['_run']:
            if len(sys.argv) != 3 or not re.fullmatch(r'job-[a-zA-Z0-9_-]+', sys.argv[2]):
                raise ValueError('Invalid local job identifier')
            work(JOB_ROOT / sys.argv[2])
        else:
            main()
    except ValueError as error:
        sys.exit(str(error))
