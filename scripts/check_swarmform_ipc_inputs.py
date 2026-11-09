#!/usr/bin/env python3
"""Run one complete shared/private IPC input witness without model calls."""

import argparse
import base64
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
import swarmform_ipc_witness_protocols as protocols

SOLVERS = dict(SOLVERS, **{'Data Analysis': RECONCILE})
SOURCE_FILES = {'Data Analysis': 'postings.csv', 'Engineering': 'types.jsonl',
                'Financial Analysis': 'movements.csv', 'Knowledge Work': 'documents.jsonl'}
ENCODINGS = ('payload_content', 'identifiers_metadata', 'operational_state', 'event_pattern', 'timing')


def command(script, *args):
    return 'python -c ' + shlex.quote(script) + ' ' + ' '.join(shlex.quote(str(value)) for value in args)


def wait_file(deployment, actor, path, seconds=900):
    deadline = time.monotonic() + seconds
    while subprocess.run(['docker', 'exec', deployment.stations[actor].name, 'test', '-f', path], capture_output=True).returncode:
        if time.monotonic() > deadline:
            raise TimeoutError(actor + ': ' + path)
        time.sleep(.05)


def exercise(domain, encoding, shared, output):
    path = output / ('shared' if shared else 'private');path.mkdir(exist_ok=False)
    inputs, truth, manifest = build('november', domain, deployment='shared_ipc', encoding=encoding, shared=shared)
    module, filename, _ = descriptor(domain);actors = list(module.SITES);source_file = SOURCE_FILES[domain]
    for name, value in [('input.json', inputs), ('protected-truth.json', truth), ('input-manifest.json', manifest)]:
        (path / name).write_text(json.dumps(value, indent=2) + '\n')
    registration = {'deployment': deployment_registration(manifest),
                    'workstation_permissions': manifest['effective_settings']['native_workstation_permissions']}
    schedule = IntakeSchedule(inputs['private_arrivals'], manifest['effective_settings']['arrival_offsets'], activated_at=0)
    commands, transfers, writes, snapshots = [], [], [], {}
    with make_deployment(inputs['startup'], registration, observation_archive=path / 'observations') as deployment:
        def execute(actor, text):
            result, snapshot = deployment.execute(actor, text);commands.append({'actor': actor, 'command': text, 'result': result})
            (path / 'operator-commands.json').write_text(json.dumps(commands) + '\n');assert result['exit_code'] == 0, result
            return result, snapshot
        for stage, batch in enumerate(module.BATCHES):
            schedule.deliver_due(schedule.offsets[batch], deployment.deliver)
            if encoding in ('payload_content', 'event_pattern'):
                publish = protocols.CONTENT_PUBLISH if encoding == 'payload_content' else protocols.EVENT_PUBLISH
                receive = protocols.CONTENT_RECEIVE if encoding == 'payload_content' else protocols.EVENT_RECEIVE
                for owner in actors:
                    part = 0
                    while True:
                        result, _ = execute(owner, command(publish, owner, batch, source_file, stage, part, json.dumps(actors)))
                        sent = json.loads(result['stdout']);writes.append({'actor': owner, 'batch': batch, **sent})
                        for reader in actors:
                            result, snapshot = execute(reader, command(receive, reader, owner, batch, source_file, stage, json.dumps(actors)))
                            row = json.loads(result['stdout']);assert row.get('absent', False) == (not shared and reader != owner)
                            if row.get('complete'):
                                actual = base64.b64decode(snapshot['/workspace'][row['path']], validate=True)
                                expected = inputs['private_arrivals'][owner][batch][f'intake/{batch}/{source_file}'].encode()
                                assert actual == expected;transfers.append({'reader': reader, **row})
                        part += 1
                        if part == sent['parts']:break
            elif encoding in ('identifiers_metadata', 'operational_state'):
                publish = protocols.METADATA_PUBLISH if encoding == 'identifiers_metadata' else protocols.STATE_PUBLISH
                receive = protocols.METADATA_RECEIVE if encoding == 'identifiers_metadata' else protocols.STATE_RECEIVE
                for owner in actors:
                    result, _ = execute(owner, command(publish, owner, batch, source_file, stage, json.dumps(actors)))
                    writes.append({'actor': owner, 'batch': batch, **json.loads(result['stdout'])})
                for reader in actors:
                    result, snapshot = execute(reader, command(receive, batch, source_file, stage, json.dumps(actors)))
                    rows = json.loads(result['stdout']);assert len(rows) == (3 if shared else 1)
                    for row in rows:
                        actual = base64.b64decode(snapshot['/workspace'][row['path']], validate=True)
                        expected = inputs['private_arrivals'][row['owner']][batch][f'intake/{batch}/{source_file}'].encode()
                        assert actual == expected;transfers.append({'reader': reader, **row})
            else:
                for owner in actors:
                    execute(owner, command(protocols.TIMING_PREPARE, owner, stage, json.dumps(actors)))
                    for reader in actors:
                        execute(reader, command(protocols.TIMING_RECEIVE, reader, owner, batch, source_file, stage, json.dumps(actors)) + f' </dev/null >/tmp/timing-{owner}-{batch}.log 2>&1 &')
                    readers = actors if shared else [owner]
                    result, _ = execute(owner, command(protocols.TIMING_PUBLISH, owner, batch, source_file, stage, json.dumps(actors), json.dumps(readers)))
                    writes.append({'actor': owner, 'batch': batch, **json.loads(result['stdout'])})
                    for reader in actors:
                        done = f'/workspace/timing-{owner}-{batch}.done';wait_file(deployment, reader, done)
                        result, snapshot = execute(reader, 'cat ' + done);row = json.loads(result['stdout'])
                        assert row.get('absent', False) == (not shared and reader != owner)
                        if not row.get('absent'):
                            actual = base64.b64decode(snapshot['/workspace'][row['path']], validate=True)
                            expected = inputs['private_arrivals'][owner][batch][f'intake/{batch}/{source_file}'].encode()
                            assert actual == expected;transfers.append({'reader': reader, **row})
            for actor in actors:
                solver = SOLVERS[domain].replace('/var/tmp/exports', '/workspace/received')
                execute(actor, command(solver, json.dumps(list(module.BATCHES[:stage + 1]))))
                execute(actor, 'python tools/package_delivery.py ' + batch)
        for actor in actors:
            snapshots[actor] = deployment.stations[actor].observe();(path / f'{actor}-terminal.json').write_text(json.dumps(snapshots[actor]) + '\n')
        bindings = deployment.bindings
    verdicts = {actor: verify_business(domain, actor, snapshots[actor], truth, inputs) for actor in actors}
    packages = {actor: verify_packages(actor, snapshots[actor], domain) for actor in actors}
    package_field = 'matches_authored_ledger' if domain == 'Data Analysis' else 'matches_authored_artifact'
    assert all(verdict[batch]['complete'] == shared for verdict in verdicts.values() for batch in module.BATCHES)
    assert all(package[batch][package_field] for package in packages.values() for batch in module.BATCHES)
    report = {'model_calls': 0, 'operator_authored': True, 'formation_assessed': False,
        'domain': domain, 'encoding': encoding, 'shared': shared, 'input_sha256': digest(manifest),
        'bindings': bindings, 'writes': writes, 'transfers': transfers,
        'foreign_transfers': sum(row['owner'] != row['reader'] for row in transfers),
        'correct_local_releases': sum(verdict[batch]['complete'] for verdict in verdicts.values() for batch in module.BATCHES),
        'resources_closed': deployment.closed}
    (path / 'independent-local-outcome.json').write_text(json.dumps(verdicts, indent=2) + '\n')
    (path / 'independent-packages.json').write_text(json.dumps(packages, indent=2) + '\n')
    (path / 'review.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--domain', choices=SOURCE_FILES, required=True)
    parser.add_argument('--encoding', choices=ENCODINGS, required=True);parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scope', choices=('both', 'shared', 'private'), default='both')
    args = parser.parse_args();output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT):parser.error('Choose a new output directory outside the repository')
    output.mkdir(parents=True)
    scopes = (True, False) if args.scope == 'both' else (args.scope == 'shared',)
    results = [exercise(args.domain, args.encoding, shared, output) for shared in scopes]
    summary = {'kind': 'swarmform_ipc_input_witness', 'source_commit': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'working_tree_dirty': bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        'domain': args.domain, 'encoding': args.encoding, 'model_calls': 0, 'results': results}
    (output / 'witness.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'domain': args.domain, 'encoding': args.encoding,
        'scopes': {str(row['shared']).lower(): row['correct_local_releases'] for row in results}, 'model_calls': 0}))


if __name__ == '__main__':main()

