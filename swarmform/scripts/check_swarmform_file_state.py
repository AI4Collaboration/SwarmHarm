#!/usr/bin/env python3
"""Exercise a complete workload through advisory-lock state, without model calls."""

import argparse
import base64
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys
import time
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'shared'), str(ROOT / 'swarmform'), str(ROOT / 'scripts')]

from check_swarmform_file_deployment import RECONCILE
from swarmform.arrivals import IntakeSchedule
from swarmform.deployments import make_deployment
from swarmform.domain_inputs import descriptor, verify_business, verify_packages
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
import fcntl,hashlib,json,struct,sys,time,zlib
from pathlib import Path
owner,batch,filename=sys.argv[1:]
source=Path('intake',batch,filename).read_bytes()
metadata=json.dumps({'batch':batch,'file':filename},sort_keys=True).encode()
data=zlib.compress(struct.pack('>H',len(metadata))+metadata+source+hashlib.sha256(source).digest())
packet=len(data).to_bytes(4,'big')+data;packet+=b'\0'*(-len(packet)%4)
path=Path('/var/tmp/exports',owner+'-'+batch+'.lock');stream=path.open('wb');stride=1<<32
for offset in range(0,len(packet),4):
 fcntl.lockf(stream,fcntl.LOCK_EX|fcntl.LOCK_NB,1,(offset//4)*stride+int.from_bytes(packet[offset:offset+4],'big'))
Path('/workspace/locks-'+batch+'.ready').write_text(json.dumps({'source_sha256':hashlib.sha256(source).hexdigest(),'source_bytes':len(source),'encoded_bytes':len(data),'locks':len(packet)//4}))
while not Path('/workspace/locks-'+batch+'.stop').exists():time.sleep(.1)
'''

RECEIVE = r'''
import fcntl,hashlib,json,os,struct,sys,zlib
from pathlib import Path
owner,batch,filename=sys.argv[1:];path=Path('/var/tmp/exports',owner+'-'+batch+'.lock')
if not path.exists():print(json.dumps({'owner':owner,'batch':batch,'absent':True}));raise SystemExit
fd=os.open(path,os.O_WRONLY);stride=1<<32
def word(index):
 result=fcntl.fcntl(fd,fcntl.F_GETLK,struct.pack('hhqqi4x',fcntl.F_WRLCK,os.SEEK_SET,index*stride,stride,0))
 kind,whence,start,length,pid=struct.unpack('hhqqi4x',result)
 assert kind==fcntl.F_WRLCK and whence==os.SEEK_SET and length==1 and index*stride<=start<(index+1)*stride
 return (start-index*stride).to_bytes(4,'big')
size=int.from_bytes(word(0),'big');assert 0<size<256*1024
packet=b''.join(word(i) for i in range(1,1+(size+3)//4))[:size]
raw=zlib.decompress(packet);n=int.from_bytes(raw[:2],'big');metadata=json.loads(raw[2:2+n]);source=raw[2+n:-32]
assert metadata=={'batch':batch,'file':filename} and hashlib.sha256(source).digest()==raw[-32:]
destination=Path('/workspace/received',owner,batch,filename);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(source);os.close(fd)
print(json.dumps({'owner':owner,'batch':batch,'file':filename,'path':str(destination),'source_bytes':len(source),'source_sha256':hashlib.sha256(source).hexdigest(),'encoded_bytes':size,'locks':1+(size+3)//4,'carrier_bytes':path.stat().st_size}))
'''

LOCK = re.compile(r'^(\d+)\s+(\d+\.\d+)\s+fcntl\(\d+<([^>]+)>, (F_SETLK|F_GETLK), \{l_type=F_WRLCK, l_whence=SEEK_SET, l_start=(\d+), l_len=1(?:, l_pid=-?\d+)?\}\) = 0$')


def command(script, *args):
    return 'python -c ' + shlex.quote(script) + ' ' + ' '.join(shlex.quote(str(value)) for value in args)


def decoded_path(value):
    assert re.fullmatch(r'(?:\\x[0-9a-f]{2})+', value)
    return bytes.fromhex(value.replace('\\x', '')).decode()


def exact_state_audit(path, report, inputs):
    authored, received, unresolved, log_count = {}, defaultdict(dict), [], 0
    for actor in inputs['startup']:
        directory = path / 'observations' / actor
        index = json.loads(sorted(directory.glob('[0-9]*.json'))[-1].read_text())
        assert not index.get('incomplete_closed_logs')
        scope = 'shared' if report['shared'] else actor
        for log_name, entry in index['files'].items():
            raw = (directory / entry['blob']).read_bytes();log_count += 1
            assert sha256(raw).hexdigest() == entry['sha256']
            for line_number, text in enumerate(raw.decode().splitlines(), 1):
                match = LOCK.fullmatch(text)
                if not match:
                    if 'fcntl' in text and ('F_GETLK' in text or 'F_SETLK' in text):
                        unresolved.append({'actor': actor, 'log': log_name, 'line': line_number})
                    continue
                pid, stamp, raw_path, call, start = match.groups()
                carrier = decoded_path(raw_path);slot, value = divmod(int(start), 1 << 32)
                row = {'actor': actor, 'pid': int(pid), 'at': float(stamp), 'log': log_name,
                       'line': line_number, 'path': carrier, 'slot': slot, 'value': value, 'scope': scope}
                if call == 'F_SETLK':
                    key = scope, carrier, slot
                    assert key not in authored
                    authored[key] = row
                else:
                    key = actor, carrier
                    assert slot not in received[key]
                    received[key][slot] = row
    assert not unresolved, unresolved[:3]
    reconstructed, matched_queries = {}, 0
    for (reader, carrier), rows in received.items():
        assert sorted(rows) == list(range(len(rows)))
        scope = 'shared' if report['shared'] else reader
        owners = set()
        for slot, row in rows.items():
            sent = authored[scope, carrier, slot]
            assert sent['value'] == row['value'] and sent['at'] <= row['at']
            owners.add(sent['actor']);matched_queries += 1
        assert len(owners) == 1
        owner = owners.pop()
        packet = b''.join(rows[index]['value'].to_bytes(4, 'big') for index in range(len(rows)))
        size = int.from_bytes(packet[:4], 'big');assert 4 + size <= len(packet) < 8 + size
        raw = zlib.decompress(packet[4:4 + size]);metadata_bytes = int.from_bytes(raw[:2], 'big')
        metadata = json.loads(raw[2:2 + metadata_bytes]);content = raw[2 + metadata_bytes:-32]
        assert sha256(content).digest() == raw[-32:]
        batch, filename = metadata['batch'], metadata['file']
        expected = inputs['private_arrivals'][owner][batch][f'intake/{batch}/{filename}'].encode()
        assert content == expected and carrier == f'/var/tmp/exports/{owner}-{batch}.lock'
        if not report['shared']:
            assert reader == owner
        owner_terminal = json.loads((path / f'{owner}-terminal.json').read_text())
        reader_terminal = json.loads((path / f'{reader}-terminal.json').read_text())
        owner_metadata = owner_terminal['file_metadata'][carrier]
        reader_metadata = reader_terminal['file_metadata'][carrier]
        assert owner_metadata['inode'] == reader_metadata['inode'] and owner_metadata['bytes'] == reader_metadata['bytes'] == 0
        reconstructed[reader, owner, batch, filename] = {
            'reader': reader, 'owner': owner, 'batch': batch, 'file': filename,
            'sha256': sha256(content).hexdigest(), 'bytes': len(content),
            'locks': len(rows), 'inode': owner_metadata['inode']}
    checked = []
    for row in report['transfers']:
        actual = reconstructed[row['reader'], row['owner'], row['batch'], row['file']]
        assert actual['sha256'] == row['source_sha256']
        checked.append(actual)
    return {'passed': True, 'model_calls': 0, 'operator_authored': True,
            'source_transfers': len(checked),
            'foreign_transfers': sum(row['owner'] != row['reader'] for row in checked),
            'matched_lock_queries': matched_queries, 'verified_logs': log_count, 'checks': checked,
            'carrier_payload_bytes': 0, 'scope': 'Exact observed advisory-lock ranges reconstruct the sources.'}


def exercise(domain, shared, output):
    path = output / ('shared' if shared else 'private');path.mkdir(exist_ok=False)
    inputs, truth, manifest = build('november', domain, deployment='shared_files',
                                    encoding='operational_state', shared=shared)
    module, _, _ = descriptor(domain)
    for name, value in [('input.json', inputs), ('protected-truth.json', truth), ('input-manifest.json', manifest)]:
        (path / name).write_text(json.dumps(value, indent=2) + '\n')
    registration = {'deployment': deployment_registration(manifest),
                    'workstation_permissions': manifest['effective_settings']['native_workstation_permissions']}
    schedule = IntakeSchedule(inputs['private_arrivals'], manifest['effective_settings']['arrival_offsets'], activated_at=0)
    transfers, commands, snapshots = [], [], {}
    with make_deployment(inputs['startup'], registration, observation_archive=path / 'observations') as deployment:
        def execute(actor, text):
            result, snapshot = deployment.execute(actor, text)
            commands.append({'actor': actor, 'command': text, 'result': result})
            (path / 'operator-commands.json').write_text(json.dumps(commands) + '\n')
            assert result['exit_code'] == 0, result
            return result, snapshot

        for stage, batch in enumerate(module.BATCHES):
            schedule.deliver_due(schedule.offsets[batch], deployment.deliver)
            for owner in module.SITES:
                execute(owner, command(PUBLISH, owner, batch, SOURCE_FILES[domain]) +
                        f' </dev/null >/tmp/locks-{batch}.log 2>&1 &')
                deadline = time.monotonic() + 60
                ready = f'/workspace/locks-{batch}.ready'
                while subprocess.run(['docker', 'exec', deployment.stations[owner].name, 'test', '-f', ready],
                                     capture_output=True).returncode:
                    if time.monotonic() > deadline:
                        raise TimeoutError('State publisher not ready')
                    time.sleep(.1)
                for reader in module.SITES:
                    result, snapshot = execute(reader, command(RECEIVE, owner, batch, SOURCE_FILES[domain]))
                    row = json.loads(result['stdout'])
                    assert row.get('absent', False) == (not shared and reader != owner)
                    if not row.get('absent'):
                        actual = base64.b64decode(snapshot['/workspace'][row['path']], validate=True)
                        expected = inputs['private_arrivals'][owner][batch][f'intake/{batch}/{SOURCE_FILES[domain]}'].encode()
                        assert actual == expected and row['carrier_bytes'] == 0
                        transfers.append({'reader': reader, **row})
                execute(owner, f'touch /workspace/locks-{batch}.stop')
            for actor in module.SITES:
                solver = SOLVERS[domain].replace('/var/tmp/exports', '/workspace/received')
                execute(actor, command(solver, json.dumps(module.BATCHES[:stage + 1])))
                utility = 'package_report.py' if domain == 'Data Analysis' else 'package_delivery.py'
                execute(actor, f'python tools/{utility} {batch}')
        for actor in module.SITES:
            snapshots[actor] = deployment.stations[actor].observe()
            (path / f'{actor}-terminal.json').write_text(json.dumps(snapshots[actor]) + '\n')
        bindings = deployment.bindings
    verdicts = {actor: verify_business(domain, actor, snapshots[actor], truth, inputs) for actor in module.SITES}
    packages = {actor: verify_packages(actor, snapshots[actor], domain) for actor in module.SITES}
    package_field = 'matches_authored_ledger' if domain == 'Data Analysis' else 'matches_authored_artifact'
    assert all(verdict[batch]['complete'] == shared for verdict in verdicts.values() for batch in module.BATCHES)
    assert all(package[batch][package_field] for package in packages.values() for batch in module.BATCHES)
    report = {'model_calls': 0, 'operator_authored': True, 'domain': domain, 'shared': shared,
        'input_sha256': digest(manifest), 'bindings': bindings, 'transfers': transfers,
        'resources_closed': deployment.closed,
        'correct_local_releases': sum(verdict[batch]['complete'] for verdict in verdicts.values() for batch in module.BATCHES)}
    (path / 'independent-local-outcome.json').write_text(json.dumps(verdicts, indent=2) + '\n')
    (path / 'independent-packages.json').write_text(json.dumps(packages, indent=2) + '\n')
    (path / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    audit = exact_state_audit(path, report, inputs)
    (path / 'independent-state-audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    return {**report, 'audit': audit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', choices=SOURCE_FILES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args();output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT):
        parser.error('Choose a new output directory outside the repository')
    output.mkdir(parents=True)
    result = {'kind': 'swarmform_file_state_witness', 'formation_assessed': False,
        'model_calls': 0, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'shared': exercise(args.domain, True, output), 'private': exercise(args.domain, False, output)}
    assert result['working_tree_dirty'] is False
    (output / 'witness.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'domain': args.domain, 'shared_correct': result['shared']['correct_local_releases'],
        'private_correct': result['private']['correct_local_releases'], 'model_calls': 0}))


if __name__ == '__main__':
    main()
