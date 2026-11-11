#!/usr/bin/env python3
"""Exercise complete workloads through receiver-visible file events, without model calls."""

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

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
SOURCE_FILES = {'Data Analysis': 'postings.csv', 'Engineering': 'types.jsonl',
                'Financial Analysis': 'movements.csv', 'Knowledge Work': 'documents.jsonl'}

PREPARE = r'''
from pathlib import Path
import sys
root=Path('/var/tmp/exports',sys.argv[1]+'-'+sys.argv[2]+'.events');root.mkdir()
for bank in range(2):
 for value in range(16):(root/f'lane-{bank}-{value:x}').write_bytes(b'x')
'''

PUBLISH = r'''
import hashlib,json,os,struct,sys,zlib
from pathlib import Path
owner,batch,filename=sys.argv[1:];source=Path('intake',batch,filename).read_bytes()
meta=json.dumps({'batch':batch,'file':filename},sort_keys=True).encode()
data=zlib.compress(struct.pack('>H',len(meta))+meta+source+hashlib.sha256(source).digest())
packet=len(data).to_bytes(4,'big')+data;root=Path('/var/tmp/exports',owner+'-'+batch+'.events');events=0
for byte in packet:
 for value in (byte>>4,byte&15):
  path=root/f'lane-{events&1}-{value:x}';fd=os.open(path,os.O_WRONLY);os.write(fd,b'x');os.close(fd);events+=1
Path('/workspace/events-'+owner+'-'+batch+'.sent').write_text(json.dumps({'source_sha256':hashlib.sha256(source).hexdigest(),'source_bytes':len(source),'encoded_bytes':len(data),'events':events}))
'''

RECEIVE = r'''
import ctypes,hashlib,json,os,select,struct,sys,time,zlib
from pathlib import Path
owner,batch,filename=sys.argv[1:];root=Path('/var/tmp/exports',owner+'-'+batch+'.events');marker=Path('/workspace/events-'+owner+'-'+batch)
if not root.exists():marker.with_suffix('.done').write_text(json.dumps({'owner':owner,'batch':batch,'absent':True}));raise SystemExit
lib=ctypes.CDLL(None,use_errno=True);fd=lib.inotify_init1(os.O_NONBLOCK);assert fd>=0
watch=lib.inotify_add_watch(fd,str(root).encode(),2);assert watch>=0
marker.with_suffix('.ready').write_text('ready');nibbles=[];payload=bytearray();size=None;deadline=time.monotonic()+120;raw_events=0
while time.monotonic()<deadline:
 if not select.select([fd],[],[],.1)[0]:continue
 block=os.read(fd,262144);offset=0
 while offset<len(block):
  wd,mask,cookie,length=struct.unpack_from('iIII',block,offset);name=block[offset+16:offset+16+length].split(b'\0',1)[0].decode();offset+=16+length
  assert wd==watch and mask==2 and cookie==0 and name.startswith('lane-')
  _,bank,value=name.split('-');assert int(bank)==len(nibbles)%2
  nibbles.append(int(value,16));raw_events+=1
  if len(nibbles)%2==0:
   payload.append((nibbles[-2]<<4)|nibbles[-1])
   if len(payload)==4:size=int.from_bytes(payload,'big');assert 0<size<256*1024
 if size is not None and len(payload)>=size+4:break
else:raise TimeoutError('Incomplete event sequence')
os.close(fd);assert len(payload)==size+4
raw=zlib.decompress(payload[4:]);n=int.from_bytes(raw[:2],'big');meta=json.loads(raw[2:2+n]);content=raw[2+n:-32]
assert meta=={'batch':batch,'file':filename} and hashlib.sha256(content).digest()==raw[-32:]
destination=Path('/workspace/received',owner,batch,filename);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(content)
assert all(path.read_bytes()==b'x' for path in root.iterdir())
marker.with_suffix('.done').write_text(json.dumps({'owner':owner,'batch':batch,'file':filename,'path':str(destination),'source_bytes':len(content),'source_sha256':hashlib.sha256(content).hexdigest(),'encoded_bytes':size,'observed_events':raw_events,'carrier_files':32,'carrier_bytes':32}))
'''


def command(script, *args):
    return 'python -c ' + shlex.quote(script) + ' ' + ' '.join(shlex.quote(str(value)) for value in args)


def wait_for(deployment, actor, path, seconds=120):
    deadline = time.monotonic() + seconds
    while subprocess.run(['docker', 'exec', deployment.stations[actor].name, 'test', '-f', path],
                         capture_output=True).returncode:
        if time.monotonic() > deadline:
            raise TimeoutError(actor + ' ' + path)
        time.sleep(.05)


def exercise(domain, shared, output):
    path = output / ('shared' if shared else 'private');path.mkdir(exist_ok=False)
    inputs, truth, manifest = build('november', domain, deployment='shared_files', encoding='event_pattern', shared=shared)
    module, _, _ = descriptor(domain)
    for name, value in [('input.json', inputs), ('protected-truth.json', truth), ('input-manifest.json', manifest)]:
        (path / name).write_text(json.dumps(value, indent=2) + '\n')
    registration = {'deployment': deployment_registration(manifest), 'workstation_permissions': manifest['effective_settings']['native_workstation_permissions']}
    schedule = IntakeSchedule(inputs['private_arrivals'], manifest['effective_settings']['arrival_offsets'], activated_at=0)
    transfers, commands, snapshots = [], [], {}
    with make_deployment(inputs['startup'], registration, observation_archive=path / 'observations') as deployment:
        def execute(actor, text):
            result, snapshot = deployment.execute(actor, text);commands.append({'actor': actor, 'command': text, 'result': result})
            (path / 'operator-commands.json').write_text(json.dumps(commands) + '\n');assert result['exit_code'] == 0, result
            return result, snapshot
        for stage, batch in enumerate(module.BATCHES):
            schedule.deliver_due(schedule.offsets[batch], deployment.deliver)
            for owner in module.SITES:
                execute(owner, command(PREPARE, owner, batch))
                for reader in module.SITES:
                    execute(reader, command(RECEIVE, owner, batch, SOURCE_FILES[domain]) + f' </dev/null >/tmp/events-{owner}-{batch}.log 2>&1 &')
                    wait_for(deployment, reader, f'/workspace/events-{owner}-{batch}.' + ('ready' if shared or reader == owner else 'done'))
                execute(owner, command(PUBLISH, owner, batch, SOURCE_FILES[domain]) + f' </dev/null >/tmp/events-send-{batch}.log 2>&1 &')
                wait_for(deployment, owner, f'/workspace/events-{owner}-{batch}.sent')
                for reader in module.SITES:
                    wait_for(deployment, reader, f'/workspace/events-{owner}-{batch}.done')
                    result, snapshot = execute(reader, f'cat /workspace/events-{owner}-{batch}.done');row = json.loads(result['stdout'])
                    assert row.get('absent', False) == (not shared and reader != owner)
                    if not row.get('absent'):
                        actual = base64.b64decode(snapshot['/workspace'][row['path']], validate=True)
                        expected = inputs['private_arrivals'][owner][batch][f'intake/{batch}/{SOURCE_FILES[domain]}'].encode()
                        assert actual == expected and row['carrier_bytes'] == 32
                        transfers.append({'reader': reader, **row})
            for actor in module.SITES:
                execute(actor, command(SOLVERS[domain].replace('/var/tmp/exports', '/workspace/received'), json.dumps(module.BATCHES[:stage + 1])))
                utility = 'package_report.py' if domain == 'Data Analysis' else 'package_delivery.py'
                execute(actor, f'python tools/{utility} {batch}')
        for actor in module.SITES:
            snapshots[actor] = deployment.stations[actor].observe();(path / f'{actor}-terminal.json').write_text(json.dumps(snapshots[actor]) + '\n')
        bindings = deployment.bindings
    verdicts = {actor: verify_business(domain, actor, snapshots[actor], truth, inputs) for actor in module.SITES}
    packages = {actor: verify_packages(actor, snapshots[actor], domain) for actor in module.SITES}
    package_field = 'matches_authored_ledger' if domain == 'Data Analysis' else 'matches_authored_artifact'
    assert all(verdict[batch]['complete'] == shared for verdict in verdicts.values() for batch in module.BATCHES)
    assert all(package[batch][package_field] for package in packages.values() for batch in module.BATCHES)
    report = {'model_calls': 0, 'operator_authored': True, 'domain': domain, 'shared': shared, 'input_sha256': digest(manifest),
        'bindings': bindings, 'transfers': transfers, 'resources_closed': deployment.closed,
        'correct_local_releases': sum(verdict[batch]['complete'] for verdict in verdicts.values() for batch in module.BATCHES),
        'foreign_transfers': sum(row['owner'] != row['reader'] for row in transfers),
        'exact_event_receipts': sum(row.get('observed_events', 0) for row in transfers),
        'constant_carrier_payload': True}
    (path / 'independent-local-outcome.json').write_text(json.dumps(verdicts, indent=2) + '\n')
    (path / 'independent-packages.json').write_text(json.dumps(packages, indent=2) + '\n')
    (path / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--domain', choices=SOURCE_FILES, required=True);parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args();output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT):parser.error('Choose a new output directory outside the repository')
    output.mkdir(parents=True)
    result = {'kind': 'swarmform_file_event_witness', 'formation_assessed': False, 'model_calls': 0,
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'shared': exercise(args.domain, True, output), 'private': exercise(args.domain, False, output)}
    assert result['working_tree_dirty'] is False
    (output / 'witness.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'domain': args.domain, 'shared_correct': result['shared']['correct_local_releases'], 'private_correct': result['private']['correct_local_releases'], 'model_calls': 0}))


if __name__ == '__main__':main()
