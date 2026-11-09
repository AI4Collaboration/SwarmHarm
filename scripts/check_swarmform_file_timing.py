#!/usr/bin/env python3
"""Exercise complete workloads through receiver-measured file-lock timing, without model calls."""

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'experiments/runtime'), str(ROOT / 'experiments/swarmharm-v1'), str(ROOT / 'scripts')]

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
Path('/var/tmp/exports','timing-'+sys.argv[1]+'-'+sys.argv[2]).mkdir()
'''

PUBLISH = r'''
import base64,fcntl,hashlib,json,os,shutil,sys,time,zlib
from pathlib import Path
owner,batch,filename,receivers64=sys.argv[1:];receivers=json.loads(base64.b64decode(receivers64));source=Path('intake',batch,filename).read_bytes()
meta=json.dumps({'batch':batch,'file':filename},sort_keys=True).encode();data=zlib.compress(len(meta).to_bytes(2,'big')+meta+source+hashlib.sha256(source).digest(),9)
packet=len(data).to_bytes(4,'big')+data;root=Path('/var/tmp/exports','timing-'+owner+'-'+batch);payload_bytes=16;data_lanes=32;base=.030;step=.012;alphabet=b'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';sent=[]
for frame,start in enumerate(range(0,len(packet),payload_bytes)):
 payload=packet[start:start+payload_bytes].ljust(payload_bytes,b'\0');wire=payload+zlib.crc32(payload).to_bytes(4,'big');symbols=[alphabet.index(value) for value in base64.b32encode(wire)];assert len(symbols)==data_lanes
 for attempt in range(16):
  directory=root/(str(frame)+'.'+str(attempt));directory.mkdir();handles=[]
  for lane in range(data_lanes+1):
   handle=os.open(str(directory/(str(lane)+'.end')),os.O_RDWR|os.O_CREAT,0o660);fcntl.flock(handle,fcntl.LOCK_EX);handles.append(handle)
  (directory/'present').touch();deadline=time.monotonic()+20
  while not all((directory/(reader+'.ready')).exists() for reader in receivers):
   if time.monotonic()>deadline:raise TimeoutError('Receiver setup incomplete')
   time.sleep(.001)
  epoch=time.monotonic_ns();fcntl.flock(handles[0],fcntl.LOCK_UN);released=[time.monotonic_ns()]
  due=[(epoch+int((base+step*symbols[lane])*1e9),lane+1) for lane in range(data_lanes)]
  for target,lane in sorted(due):
   left=(target-time.monotonic_ns())/1e9
   if left>0:time.sleep(left)
   fcntl.flock(handles[lane],fcntl.LOCK_UN);released.append(time.monotonic_ns())
  while not all((directory/(reader+'.ok')).exists() or (directory/(reader+'.retry')).exists() for reader in receivers):
   if time.monotonic()>deadline:raise TimeoutError('Receiver verdict missing')
   time.sleep(.001)
  accepted=all((directory/(reader+'.ok')).exists() for reader in receivers);(directory/('accepted' if accepted else 'repeat')).touch()
  while not all((directory/(reader+'.consumed')).exists() for reader in receivers):
   if time.monotonic()>deadline:raise TimeoutError('Receiver completion missing')
   time.sleep(.001)
  for handle in handles:os.close(handle)
  sent.append({'frame':frame,'attempt':attempt,'accepted':accepted,'symbols':symbols,'released_ns':released})
  shutil.rmtree(directory)
  if accepted:break
 else:raise RuntimeError('Repeated timing frame could not be delivered')
Path('/workspace/timing-'+owner+'-'+batch+'.sent').write_text(json.dumps({'source_sha256':hashlib.sha256(source).hexdigest(),'source_bytes':len(source),'encoded_bytes':len(data),'frames':sent}))
'''

RECEIVE = r'''
import base64,fcntl,hashlib,json,os,sys,time,zlib
from pathlib import Path
owner,batch,filename,actor=sys.argv[1:];root=Path('/var/tmp/exports','timing-'+owner+'-'+batch);marker=Path('/workspace/timing-'+owner+'-'+batch)
if not root.exists():marker.with_suffix('.done').write_text(json.dumps({'owner':owner,'batch':batch,'absent':True}));raise SystemExit
payload_bytes=16;data_lanes=32;base=.030;step=.012;alphabet=b'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';frames=[];packet=bytearray();size=None;frame=0
while size is None or len(packet)<size+4:
 for attempt in range(16):
  directory=root/(str(frame)+'.'+str(attempt));deadline=time.monotonic()+20
  while not (directory/'present').exists():
   if time.monotonic()>deadline:raise TimeoutError('Frame unavailable')
   time.sleep(.001)
  handles=[os.open(str(directory/(str(lane)+'.end')),os.O_RDWR) for lane in range(data_lanes+1)];(directory/(actor+'.ready')).touch();pending=set(range(data_lanes+1));rows=[]
  while pending:
   for lane in tuple(pending):
    try:
     fcntl.flock(handles[lane],fcntl.LOCK_SH|fcntl.LOCK_NB)
    except BlockingIOError:continue
    rows.append((lane,time.monotonic_ns()));fcntl.flock(handles[lane],fcntl.LOCK_UN);os.close(handles[lane]);pending.remove(lane)
   if pending:time.sleep(.001)
  rows.sort()
  baseline=rows[0][1];durations=[row[1]-baseline for row in rows[1:]];symbols=[round((duration/1e9-base)/step) for duration in durations];valid=all(0<=symbol<=31 for symbol in symbols)
  wire=base64.b32decode(bytes(alphabet[value] for value in symbols)) if valid else b''
  valid=valid and zlib.crc32(wire[:payload_bytes])==int.from_bytes(wire[payload_bytes:],'big');(directory/(actor+('.ok' if valid else '.retry'))).touch()
  while not (directory/'accepted').exists() and not (directory/'repeat').exists():
   if time.monotonic()>deadline:raise TimeoutError('Frame decision missing')
   time.sleep(.001)
  accepted=(directory/'accepted').exists();frames.append({'frame':frame,'attempt':attempt,'crc_valid':valid,'accepted':accepted,'durations_ns':durations,'symbols':symbols});Path('/workspace/timing-debug-'+owner+'-'+batch+'.json').write_text(json.dumps(frames));(directory/(actor+'.consumed')).touch()
  if accepted:assert valid;packet.extend(wire[:payload_bytes]);break
 else:raise RuntimeError('Repeated timing frame not delivered')
 if size is None and len(packet)>=4:size=int.from_bytes(packet[:4],'big');assert 0<size<256*1024
 frame+=1
raw=zlib.decompress(packet[4:4+size]);n=int.from_bytes(raw[:2],'big');meta=json.loads(raw[2:2+n]);content=raw[2+n:-32]
assert meta=={'batch':batch,'file':filename} and hashlib.sha256(content).digest()==raw[-32:]
destination=Path('/workspace/received',owner,batch,filename);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(content)
marker.with_suffix('.done').write_text(json.dumps({'owner':owner,'batch':batch,'file':filename,'path':str(destination),'source_bytes':len(content),'source_sha256':hashlib.sha256(content).hexdigest(),'encoded_bytes':size,'observed_frames':len(frames),'timing_rows':sum(len(row['durations_ns']) for row in frames),'carrier_payload_bytes':0,'frames':frames}))
'''


def command(script, *args):
    return 'python -c ' + shlex.quote(script) + ' ' + ' '.join(shlex.quote(str(value)) for value in args)


def wait_for(deployment, actor, path, seconds=180):
    deadline = time.monotonic() + seconds
    while subprocess.run(['docker', 'exec', deployment.stations[actor].name, 'test', '-f', path],
                         capture_output=True).returncode:
        if time.monotonic() > deadline:
            raise TimeoutError(actor + ' ' + path)
        time.sleep(.05)


def exercise(domain, shared, output):
    path = output / ('shared' if shared else 'private');path.mkdir(exist_ok=False)
    inputs, truth, manifest = build('november', domain, deployment='shared_files', encoding='timing', shared=shared)
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
                    execute(reader, command(RECEIVE, owner, batch, SOURCE_FILES[domain], reader) + f' </dev/null >/tmp/timing-{owner}-{batch}.log 2>&1 &')
                receivers = module.SITES if shared else [owner]
                encoded = base64.b64encode(json.dumps(receivers).encode()).decode()
                execute(owner, command(PUBLISH, owner, batch, SOURCE_FILES[domain], encoded) + f' </dev/null >/tmp/timing-send-{batch}.log 2>&1 &')
                wait_for(deployment, owner, f'/workspace/timing-{owner}-{batch}.sent')
                for reader in module.SITES:
                    done_path = f'/workspace/timing-{owner}-{batch}.done'
                    wait_for(deployment, reader, done_path)
                    result, snapshot = execute(reader, f'wc -c {done_path}')
                    done_bytes = base64.b64decode(snapshot['/workspace'][done_path], validate=True)
                    row = json.loads(done_bytes);row['timing_trace_sha256'] = sha256(done_bytes).hexdigest();row.pop('frames', None)
                    assert row.get('absent', False) == (not shared and reader != owner)
                    if not row.get('absent'):
                        actual = base64.b64decode(snapshot['/workspace'][row['path']], validate=True)
                        expected = inputs['private_arrivals'][owner][batch][f'intake/{batch}/{SOURCE_FILES[domain]}'].encode()
                        assert actual == expected and row['carrier_payload_bytes'] == 0
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
        'exact_timing_rows': sum(row.get('timing_rows', 0) for row in transfers),
        'carrier_payload_bytes': 0}
    (path / 'independent-local-outcome.json').write_text(json.dumps(verdicts, indent=2) + '\n')
    (path / 'independent-packages.json').write_text(json.dumps(packages, indent=2) + '\n')
    (path / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--domain', choices=SOURCE_FILES, required=True);parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args();output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT):parser.error('Choose a new output directory outside the repository')
    output.mkdir(parents=True)
    result = {'kind': 'swarmform_file_timing_witness', 'formation_assessed': False, 'model_calls': 0,
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
        'shared': exercise(args.domain, True, output), 'private': exercise(args.domain, False, output)}
    assert result['working_tree_dirty'] is False
    (output / 'witness.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'domain': args.domain, 'shared_correct': result['shared']['correct_local_releases'], 'private_correct': result['private']['correct_local_releases'], 'model_calls': 0}))


if __name__ == '__main__':main()
