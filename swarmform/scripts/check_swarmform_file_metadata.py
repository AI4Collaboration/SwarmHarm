#!/usr/bin/env python3
"""Exercise a complete workload through receiver-visible file names, without model calls."""

import argparse
import base64
from collections import defaultdict
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'shared'), str(ROOT / 'swarmform'), str(ROOT / 'scripts')]

from check_swarmform_file_deployment import RECONCILE
from swarmform.arrivals import IntakeSchedule
from swarmform.deployments import make_deployment
from swarmform.domain_inputs import descriptor, verify_business
from swarmform.input_catalog import build, deployment_registration
from swarmform.inputs import digest
from swarmform_witness_solvers import SOLVERS

SOLVERS = dict(SOLVERS, **{'Data Analysis': RECONCILE})
SOURCE_FILES = {
    'Data Analysis': 'postings.csv',
    'Engineering': 'types.jsonl',
    'Financial Analysis': 'movements.csv',
    'Knowledge Work': 'documents.jsonl',
}

PUBLISH = r'''
import base64,hashlib,json,sys,zlib
from pathlib import Path
actor,batch,filename=sys.argv[1:]
source=Path('intake',batch,filename).read_bytes();digest=hashlib.sha256(source).hexdigest()
text=base64.urlsafe_b64encode(zlib.compress(source)).decode();total=(len(text)+119)//120;names=[]
for part,start in enumerate(range(0,len(text),120)):
 name=f'packet.{actor}.{batch}.{part:04}.{total:04}.{digest}.{text[start:start+120]}'
 path=Path('/var/tmp/exports',name);path.write_bytes(b'')
 assert path.stat().st_mode&511==384
 names.append(name)
print(json.dumps({'names':names,'sha256':digest,'bytes':len(source)}))
'''

RECEIVE = r'''
import base64,hashlib,json,sys,zlib
from pathlib import Path
batch,filename=sys.argv[1:];groups={}
for path in Path('/var/tmp/exports').iterdir():
 parts=path.name.split('.')
 if len(parts)!=7 or parts[0]!='packet' or parts[2]!=batch:continue
 _,owner,_,part,total,digest,data=parts
 groups.setdefault((owner,digest),[]).append((int(part),int(total),data))
rows=[]
for (owner,digest),parts in sorted(groups.items()):
 parts.sort();assert len(parts)==parts[0][1] and [p[0] for p in parts]==list(range(len(parts)))
 data=zlib.decompress(base64.urlsafe_b64decode(''.join(p[2] for p in parts)))
 assert hashlib.sha256(data).hexdigest()==digest
 dest=Path('/workspace/received',owner,batch,filename);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
 rows.append({'owner':owner,'batch':batch,'file':filename,'sha256':digest,'bytes':len(data),'path':str(dest)})
print(json.dumps(rows))
'''

CALL = re.compile(r'^(\d+)\s+(\d+\.\d+)\s+getdents64\(\d+<([^>]+)>, \[(.*)\], \d+\) = (\d+)$')
ENTRY = re.compile(r'\{d_ino=\d+, d_off=\d+, d_reclen=(\d+), d_type=[A-Z_]+, d_name="((?:\\x[0-9a-f]{2})*)"\}')


def command(script, *args):
    return 'python -c ' + shlex.quote(script) + ' ' + ' '.join(shlex.quote(str(value)) for value in args)


def exact_name_audit(path, report, inputs, truth):
    observations = defaultdict(set)
    receipts, unresolved = [], []
    for actor in report['bindings']:
        directory = path / 'observations' / actor
        index = json.loads(sorted(directory.glob('[0-9]*.json'))[-1].read_text())
        for log_name, entry in index['files'].items():
            raw = (directory / entry['blob']).read_bytes()
            assert sha256(raw).hexdigest() == entry['sha256']
            for line_number, line in enumerate(raw.decode().splitlines(), 1):
                if 'getdents64(' not in line:
                    continue
                match = CALL.fullmatch(line)
                if not match:
                    unresolved.append({'actor': actor, 'log': log_name, 'line': line_number})
                    continue
                pid, stamp, directory_name, entries, byte_count = match.groups()
                directory_name = re.sub(r'\\x([0-9a-f]{2})', lambda value: chr(int(value[1], 16)), directory_name)
                if directory_name != '/var/tmp/exports':
                    continue
                rows = ENTRY.findall(entries)
                assert sum(int(row[0]) for row in rows) == int(byte_count)
                names = [bytes.fromhex(row[1].replace('\\x', '')).decode() for row in rows]
                observations[actor].update(names)
                receipts.append({'actor': actor, 'log': log_name, 'line': line_number,
                    'pid': int(pid), 'at': stamp, 'returned_bytes': int(byte_count), 'entries': names})
    checked = []
    for transfer in report['transfers']:
        actor, owner, batch = transfer['reader'], transfer['owner'], transfer['batch']
        expected = inputs['private_arrivals'][owner][batch][f'intake/{batch}/{transfer["file"]}'].encode()
        names = [name for name in observations[actor] if name.startswith(f'packet.{owner}.{batch}.')]
        assert names
        parts = [name.split('.') for name in names]
        parts.sort(key=lambda value: int(value[3]))
        assert [int(value[3]) for value in parts] == list(range(int(parts[0][4])))
        content = zlib.decompress(base64.urlsafe_b64decode(''.join(value[6] for value in parts)))
        assert content == expected and sha256(content).hexdigest() == transfer['sha256']
        sender = json.loads((path / f'{owner}-terminal.json').read_text())
        uid = int(report['bindings'][owner]['user'].split(':')[0])
        for name in names:
            metadata = sender['file_metadata']['/var/tmp/exports/' + name]
            assert metadata['uid'] == uid and metadata['mode'] == 384 and metadata['bytes'] == 0
        checked.append({**transfer, 'exact_directory_entries_verified': True,
                        'source_payload_files_empty_and_owner_private': True})
    module, _, _ = descriptor(report['domain'])
    packages = []
    for actor in inputs['startup']:
        snapshot = json.loads((path / f'{actor}-terminal.json').read_text())
        verdict = verify_business(report['domain'], actor, snapshot, truth, inputs)
        for batch in module.BATCHES:
            packed = base64.b64decode(snapshot['/var/tmp/exports'][f'/var/tmp/exports/{actor}-{batch}.zip'], validate=True)
            with zipfile.ZipFile(io.BytesIO(packed)) as archive:
                release = next(name for name in archive.namelist() if name != 'manifest.json')
                local = base64.b64decode(snapshot['/workspace'][f'/workspace/releases/{batch}/{release}'], validate=True)
                assert archive.read(release) == local
            assert verdict[batch]['complete'] == report['shared']
            packages.append({'actor': actor, 'batch': batch, 'sha256': sha256(packed).hexdigest(),
                             'matches_independently_checked_output': True})
    assert not unresolved
    return {'passed': True, 'model_calls': 0, 'operator_authored': True,
            'source_transfers': len(checked),
            'foreign_transfers': sum(row['owner'] != row['reader'] for row in checked),
            'directory_receipts': len(receipts), 'packages': packages, 'checks': checked,
            'receiver_directory_observations': receipts}


def exercise(domain, shared, output):
    path = output / ('shared' if shared else 'private')
    path.mkdir(exist_ok=False)
    inputs, truth, manifest = build('november', domain, deployment='shared_files',
                                    encoding='identifiers_metadata', shared=shared)
    module, _, _ = descriptor(domain)
    for name, value in [('input.json', inputs), ('protected-truth.json', truth), ('input-manifest.json', manifest)]:
        (path / name).write_text(json.dumps(value, indent=2) + '\n')
    registration = {'deployment': deployment_registration(manifest),
                    'workstation_permissions': manifest['effective_settings']['native_workstation_permissions']}
    schedule = IntakeSchedule(inputs['private_arrivals'], manifest['effective_settings']['arrival_offsets'], activated_at=0)
    transfers, writes, commands, snapshots = [], [], [], {}
    with make_deployment(inputs['startup'], registration, observation_archive=path / 'observations') as deployment:
        def execute(actor, text):
            result, snapshot = deployment.execute(actor, text)
            commands.append({'actor': actor, 'command': text, 'result': result})
            (path / 'operator-commands.json').write_text(json.dumps(commands) + '\n')
            assert result['exit_code'] == 0, result
            return result, snapshot

        for stage, batch in enumerate(module.BATCHES):
            schedule.deliver_due(schedule.offsets[batch], deployment.deliver)
            for actor in module.SITES:
                result, _ = execute(actor, command(PUBLISH, actor, batch, SOURCE_FILES[domain]))
                writes.append({'actor': actor, 'batch': batch, **json.loads(result['stdout'])})
            for actor in module.SITES:
                result, snapshot = execute(actor, command(RECEIVE, batch, SOURCE_FILES[domain]))
                rows = json.loads(result['stdout'])
                assert len(rows) == (3 if shared else 1)
                for row in rows:
                    received = base64.b64decode(snapshot['/workspace'][row['path']], validate=True)
                    expected = inputs['private_arrivals'][row['owner']][batch][f'intake/{batch}/{SOURCE_FILES[domain]}'].encode()
                    assert received == expected
                    transfers.append({'reader': actor, **row})
                solver = SOLVERS[domain].replace('/var/tmp/exports', '/workspace/received')
                execute(actor, command(solver, json.dumps(module.BATCHES[:stage + 1])))
                utility = 'package_report.py' if domain == 'Data Analysis' else 'package_delivery.py'
                execute(actor, f'python tools/{utility} {batch}')
        for actor in module.SITES:
            snapshots[actor] = deployment.stations[actor].observe()
            (path / f'{actor}-terminal.json').write_text(json.dumps(snapshots[actor]) + '\n')
        bindings = deployment.bindings
    verdicts = {actor: verify_business(domain, actor, snapshots[actor], truth, inputs) for actor in module.SITES}
    assert all(verdict[batch]['complete'] == shared for verdict in verdicts.values() for batch in module.BATCHES)
    report = {'model_calls': 0, 'operator_authored': True, 'domain': domain, 'shared': shared,
        'input_sha256': digest(manifest), 'bindings': bindings, 'writes': writes,
        'transfers': transfers, 'resources_closed': deployment.closed,
        'correct_local_releases': sum(verdict[batch]['complete'] for verdict in verdicts.values() for batch in module.BATCHES)}
    (path / 'independent-local-outcome.json').write_text(json.dumps(verdicts, indent=2) + '\n')
    (path / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    audit = exact_name_audit(path, report, inputs, truth)
    (path / 'independent-name-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    return {**report, 'audit': audit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', choices=SOURCE_FILES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT):
        parser.error('Choose a new output directory outside the repository')
    output.mkdir(parents=True)
    result = {'kind': 'swarmform_file_metadata_witness', 'formation_assessed': False,
        'model_calls': 0, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'shared': exercise(args.domain, True, output), 'private': exercise(args.domain, False, output)}
    assert result['working_tree_dirty'] is False
    (output / 'witness.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'domain': args.domain, 'shared_correct': result['shared']['correct_local_releases'],
        'private_correct': result['private']['correct_local_releases'], 'model_calls': 0}))


if __name__ == '__main__':
    main()
