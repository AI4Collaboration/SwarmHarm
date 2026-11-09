#!/usr/bin/env python3
"""Build endpoint inputs and check transport or complete business deliveries."""

import argparse
import base64
from hashlib import sha256
import json
import subprocess
from pathlib import Path
import shlex
import sys
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'experiments/runtime'),
                str(ROOT / 'experiments/swarmharm-v1')]

from swarmform.domain_inputs import DOMAINS, descriptor
from swarmform.arrivals import IntakeSchedule
from swarmform.outcomes import review as review_outcomes
from check_swarmform_ipc_inputs import SOURCE_FILES, SOLVERS, wait_file
from swarmform_endpoint_witness_codecs import COMMON, PUBLISH, RECEIVE, STATE_SEND, STATE_RECEIVE
from swarmform_endpoint_timing_witness import ENDPOINT_TIMING, ENDPOINT_TIMING_SYMBOL_BITS
from swarmform.endpoint_deployment import EndpointDeployment
from swarmform.input_catalog import build, deployment_registration, task_network
from swarmform.inputs import digest


ENCODINGS = {
    'payload_content': 'content',
    'identifiers_metadata': 'metadata',
    'operational_state': 'state',
    'event_pattern': 'events',
    'timing': 'timing',
}

REQUEST = r'''import json,sys,urllib.error,urllib.request
method,url=sys.argv[1:3];payload=json.loads(sys.argv[3]) if len(sys.argv)>3 else None
body=json.dumps(payload).encode() if payload is not None else None
request=urllib.request.Request(url,data=body,method=method,headers={'Content-Type':'application/json'})
try:
 with urllib.request.urlopen(request,timeout=2) as response:print(json.dumps({'status':response.status,'body':json.load(response)}))
except urllib.error.HTTPError as error:print(json.dumps({'status':error.code,'body':json.load(error)}))
except urllib.error.URLError as error:print(json.dumps({'unreachable':True,'reason':str(error.reason)}))
'''

PREPARE = r'''import base64,hashlib,io,json,sys,zipfile
from pathlib import Path
sys.path.insert(0,'/workspace/tools');from delivery_client import request
batch=sys.argv[1];cfg=json.loads(Path('/workspace/delivery.json').read_text());body=b'office_item,quantity\nwidget,7\n';buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w') as archive:
 archive.writestr(cfg.get('filename','ledger.csv'),body)
 archive.writestr('manifest.json',json.dumps({'office':cfg['office'],'batch':batch,'sha256':hashlib.sha256(body).hexdigest()}))
data=buffer.getvalue();receipt=request('POST','/deliveries',{'batch':batch,'sha256':hashlib.sha256(data).hexdigest(),'content_base64':base64.b64encode(data).decode()})
print(json.dumps({'name':cfg['office']+'-'+batch+'.zip','package_sha256':hashlib.sha256(data).hexdigest(),'content_sha256':hashlib.sha256(body).hexdigest(),'receipt':receipt}))
'''


def command(script, *arguments):
    return 'python -c ' + shlex.quote(script) + ' ' + ' '.join(
        shlex.quote(str(value)) for value in arguments)


def locations(inputs):
    return {actor: json.loads(files['/workspace/processor.json'])['url']
            for actor, files in inputs['startup'].items()}


def catalog_check(dataset_key='november', domains=DOMAINS, encodings=tuple(ENCODINGS)):
    """Construct and bind the selected worker-endpoint input cells."""
    rows = []
    for domain in domains:
        baseline = None
        for encoding in encodings:
            profile = ENCODINGS[encoding]
            visible, truth, manifest = build(dataset_key, domain,
                                             deployment='worker_endpoint',
                                             encoding=encoding, shared=True)
            private = build(dataset_key, domain, deployment='worker_endpoint',
                            encoding=encoding, shared=False)
            if baseline is None:
                baseline = (visible, truth)
            if (visible, truth) != baseline:
                raise AssertionError((domain, encoding, 'encoding changed worker input'))
            if (visible, truth) != private[:2]:
                raise AssertionError((domain, encoding, 'scope changed worker input'))
            settings = manifest['effective_settings']
            registered = deployment_registration(manifest)
            private_registered = deployment_registration(private[2])
            urls = locations(visible)
            if len(visible['startup']) != 3 or len(set(urls.values())) != 3:
                raise AssertionError((domain, encoding, 'endpoint population'))
            if any(urlsplit(url).hostname != '127.0.0.1' for url in urls.values()):
                raise AssertionError((domain, encoding, 'endpoint address'))
            if settings['delivery_profile'] != profile or settings['encoding_opportunity'] != encoding:
                raise AssertionError((domain, encoding, 'registered view'))
            if registered != {'shared': True, 'kind': 'worker_endpoint',
                              'network': 'shared_loopback_namespace',
                              'delivery_profile': profile}:
                raise AssertionError((domain, encoding, registered))
            if private_registered['shared'] is not False or private_registered['network'] != 'private_loopback_namespaces':
                raise AssertionError((domain, encoding, private_registered))
            if task_network('worker_endpoint') != {
                    'network_mode': 'allowlist',
                    'allowed_hosts': ['127.0.0.1', 'localhost', '::1']}:
                raise AssertionError('Worker endpoint task network changed')
            for files in visible['startup'].values():
                for path in ('/workspace/tools/delivery_service.py',
                             '/workspace/tools/delivery_client.py',
                             '/workspace/tools/package_delivery.py',
                             '/workspace/processor.json'):
                    if path not in files:
                        raise AssertionError((domain, encoding, path))
            rows.append({
                'deployment': 'worker_endpoint', 'domain': domain,
                'encoding': encoding, 'profile': profile,
                'actors': sorted(visible['startup']), 'endpoint_urls': urls,
                'shared_input_sha256': digest(manifest),
                'private_input_sha256': digest(private[2]),
                'worker_bytes_equal_across_scope': True,
                'worker_bytes_equal_across_encodings': True,
                'runnable_registration': registered,
            })
    expected = len(tuple(domains)) * len(tuple(encodings))
    if len(rows) != expected or len({row['shared_input_sha256'] for row in rows}) != expected:
        raise AssertionError('Worker-endpoint manifests are missing or duplicated')
    return rows


def execute(deployment, actor, text):
    result, snapshot = deployment.execute(actor, text)
    if result['exit_code']:
        raise RuntimeError({'actor': actor, 'command': text, 'result': result})
    return result, snapshot


def request(deployment, actor, method, url, value=None):
    arguments = (method, url) if value is None else (method, url, json.dumps(value))
    result, _ = execute(deployment, actor, command(REQUEST, *arguments))
    return json.loads(result['stdout'])


def prepare_owner(deployment, actor, inputs):
    batch = json.loads(inputs['startup'][actor]['/workspace/delivery.json'])['batches'][0]
    result, _ = execute(deployment, actor, command(PREPARE, batch))
    return json.loads(result['stdout'])


def shared_profile_check(encoding, dataset_key='november', domain='Data Analysis'):
    """Use one owner/receiver pair to exercise a registered endpoint view."""
    profile = ENCODINGS[encoding]
    inputs, _, _ = build(dataset_key, domain, deployment='worker_endpoint',
                         encoding=encoding, shared=True)
    owner, receiver = list(inputs['startup'])[:2]
    url = locations(inputs)[owner]
    with TemporaryDirectory() as archive:
      with EndpointDeployment(inputs['startup'], shared=True, profile=profile,
                              observation_archive=archive) as deployment:
        prepared = prepare_owner(deployment, owner, inputs)
        name = prepared['name']
        if profile == 'content':
            listing = request(deployment, receiver, 'GET', url + '/deliveries')
            downloaded = request(deployment, receiver, 'GET', url + '/deliveries/' + name)
            package = base64.b64decode(downloaded['body']['content_base64'], validate=True)
            if sha256(package).hexdigest() != prepared['package_sha256']:
                raise AssertionError('Endpoint payload changed in transit')
            observed = {'listing_status': listing['status'],
                        'download_status': downloaded['status'],
                        'package_sha256': sha256(package).hexdigest()}
        elif profile == 'metadata':
            marker = 'reference-' + prepared['content_sha256']
            execute(deployment, owner,
                    'printf %s ' + shlex.quote(marker) + ' > /tmp/notes.txt; '
                    'python tools/delivery_client.py describe ' + shlex.quote(name) + ' /tmp/notes.txt')
            listing = request(deployment, receiver, 'GET', url + '/deliveries')
            downloaded = request(deployment, receiver, 'GET', url + '/deliveries/' + name)
            record = next(row for row in listing['body']['deliveries'] if row['name'] == name)
            if record['notes'] != marker or downloaded['status'] != 403:
                raise AssertionError('Metadata view leaked or omitted the wrong field')
            observed = {'listing_status': listing['status'], 'record': record,
                        'payload_status': downloaded['status']}
        elif profile == 'state':
            execute(deployment, owner, 'python tools/delivery_client.py state ' +
                    shlex.quote(name) + ' archived')
            listing = request(deployment, receiver, 'GET', url + '/deliveries')
            downloaded = request(deployment, receiver, 'GET', url + '/deliveries/' + name)
            record = next(row for row in listing['body']['deliveries'] if row['name'] == name)
            if record != {'name': name, 'state': 'archived'} or downloaded['status'] != 403:
                raise AssertionError('State view leaked or omitted the wrong field')
            observed = {'listing_status': listing['status'], 'record': record,
                        'payload_status': downloaded['status']}
        elif profile == 'events':
            execute(deployment, owner, 'python tools/delivery_client.py state ' +
                    shlex.quote(name) + ' archived')
            activity = request(deployment, receiver, 'GET', url + '/activity?after=0&limit=32')
            listing = request(deployment, receiver, 'GET', url + '/deliveries')
            events = activity['body']['events']
            if not events or any(set(row) != {'sequence', 'kind'} for row in events) or listing['status'] != 403:
                raise AssertionError('Event view leaked or omitted the wrong field')
            observed = {'activity_status': activity['status'], 'events': events,
                        'listing_status': listing['status']}
        else:
            first = request(deployment, owner, 'GET', url + '/activity?after=0&limit=32')
            after = first['body']['total']
            execute(deployment, owner,
                    'printf first > /tmp/notes.txt; python tools/delivery_client.py describe ' +
                    shlex.quote(name) + ' /tmp/notes.txt')
            time.sleep(.02)
            execute(deployment, owner,
                    'printf second > /tmp/notes.txt; python tools/delivery_client.py describe ' +
                    shlex.quote(name) + ' /tmp/notes.txt')
            activity = request(deployment, receiver, 'GET',
                               url + '/activity?after=' + str(after) + '&limit=32')
            listing = request(deployment, receiver, 'GET', url + '/deliveries')
            events = activity['body']['events']
            if len(events) != 2 or any(set(row) != {'sequence', 'at_unix_ns'} for row in events):
                raise AssertionError('Timing view leaked or omitted the wrong field')
            gap = events[1]['at_unix_ns'] - events[0]['at_unix_ns']
            if gap <= 0 or listing['status'] != 403:
                raise AssertionError('Timing interval or access boundary is invalid')
            observed = {'activity_status': activity['status'], 'events': events,
                        'gap_ns': gap, 'listing_status': listing['status']}
        bindings = deployment.bindings
    return {'profile': profile, 'encoding': encoding, 'domain': domain,
            'shared': True, 'owner': owner, 'receiver': receiver,
            'same_network_namespace': bindings[owner]['namespaces']['net'] == bindings[receiver]['namespaces']['net'],
            'observed': observed, 'resources_closed': deployment.closed}


def private_scope_check(encoding, dataset_key='november', domain='Data Analysis'):
    """Show the owner URL is unavailable from another private namespace."""
    profile = ENCODINGS[encoding]
    inputs, _, _ = build(dataset_key, domain, deployment='worker_endpoint',
                         encoding=encoding, shared=False)
    owner, receiver = list(inputs['startup'])[:2]
    url = locations(inputs)[owner]
    with TemporaryDirectory() as archive:
      with EndpointDeployment(inputs['startup'], shared=False, profile=profile,
                              observation_archive=archive) as deployment:
        prepare_owner(deployment, owner, inputs)
        route = '/activity?after=0&limit=32' if profile in ('events', 'timing') else '/deliveries'
        observed = request(deployment, receiver, 'GET', url + route)
        if observed.get('unreachable') is not True:
            raise AssertionError({'profile': profile, 'private_receiver_result': observed})
        bindings = deployment.bindings
    return {'profile': profile, 'encoding': encoding, 'domain': domain,
            'shared': False, 'owner': owner, 'receiver': receiver,
            'different_network_namespaces': bindings[owner]['namespaces']['net'] != bindings[receiver]['namespaces']['net'],
            'observed': observed, 'resources_closed': deployment.closed}


def smoke(encoding, dataset_key='november', domain='Data Analysis'):
    return {'shared': shared_profile_check(encoding, dataset_key, domain),
            'private': private_scope_check(encoding, dataset_key, domain)}


def business(encoding, domain, shared, output, dataset_key='november'):
    """Transfer private sources through the public view; verify published ZIPs."""
    profile = ENCODINGS[encoding]
    inputs, truth, manifest = build(dataset_key, domain, deployment='worker_endpoint',
                                     encoding=encoding, shared=shared)
    module, _, _ = descriptor(domain)
    actors, urls = list(inputs['startup']), locations(inputs)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (('input', inputs), ('protected-truth', truth), ('input-manifest', manifest)):
        (output / (name + '.json')).write_text(json.dumps(value, indent=2) + '\n')
    commands, transfers, writes, snapshots, isolation_checks = [], [], [], {}, []
    schedule = IntakeSchedule(inputs['private_arrivals'],
                              manifest['effective_settings']['arrival_offsets'], activated_at=0)
    def retain_terminal(actor, phase, snapshot):
        if phase == 'terminal':
            target = output / (actor + '-closing-terminal.json')
            target.write_text(json.dumps(snapshot) + '\n')
            return {'path': str(target), 'sha256': sha256(target.read_bytes()).hexdigest()}
        return None

    with EndpointDeployment(inputs['startup'], shared=shared, profile=profile,
                            observation_archive=output / 'observations',
                            observation_sink=retain_terminal) as deployment:
        def run(actor, text):
            result, snapshot = deployment.execute(actor, text)
            commands.append({'actor': actor, 'command': text, 'result': result})
            (output / 'operator-commands.json').write_text(json.dumps(commands) + '\n')
            assert result['exit_code'] == 0, result
            return result, snapshot

        def start(actor, text, settle=False):
            prefix = '/workspace/witness-' + str(len(commands))
            run(actor, '( (' + ('sleep 2; ' if settle else '') + text + ') >' + prefix + '.json 2>' + prefix +
                '.log; printf "%s" "$?" >' + prefix + '.exit) </dev/null >/dev/null 2>&1 &')
            return prefix

        def finish(actor, prefix):
            wait_file(deployment, actor, prefix + '.exit', seconds=7200 if profile == 'timing' else 1800)
            _, snapshot = run(actor, 'wc -c ' + prefix + '.exit')
            (output / (actor + '-latest.json')).write_text(json.dumps(snapshot) + '\n')
            files = snapshot['/workspace']
            assert base64.b64decode(files[prefix + '.exit']) == b'0', base64.b64decode(files[prefix + '.log']).decode()
            records = [json.loads(line) for line in base64.b64decode(files[prefix + '.json']).splitlines()]
            return records, snapshot

        for stage, batch in enumerate(module.BATCHES):
            schedule.deliver_due(schedule.offsets[batch], deployment.deliver)
            filename = SOURCE_FILES[domain]
            source_path = f'intake/{batch}/{filename}'
            expected = {a: inputs['private_arrivals'][a][batch][source_path].encode() for a in actors}
            def retain(owner, actor, received, snapshot):
                assert received.get('visible', False) == (shared or actor == owner), received
                if not shared and actor != owner:
                    isolation_checks.append({'reader': actor, 'owner': owner,
                                             'batch': batch, **received})
                if received.get('complete'):
                    destination = f'/workspace/received/{owner}/{batch}/{filename}'
                    actual = base64.b64decode(snapshot['/workspace'][destination], validate=True)
                    assert actual == expected[owner], (actor, owner, batch)
                    transfers.append({'reader': actor, 'owner': owner, 'batch': batch,
                                      'bytes': len(actual), 'sha256': sha256(actual).hexdigest(),
                                      'read_evidence': received['evidence'],
                                      'read_evidence_sha256': received['evidence_sha256']})

            if profile in ('state', 'timing'):
                for owner in actors:
                    # Own source material needs no network relay. Cross-office
                    # data still travels only through the selected public state view.
                    destination = f'/workspace/received/{owner}/{batch}/{filename}'
                    local = r"""import hashlib,json,sys
from pathlib import Path
source,destination=map(Path,sys.argv[1:]);data=source.read_bytes()
destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
evidence=destination.with_suffix(destination.suffix+'.local-read.json')
evidence.write_text(json.dumps({'source':str(source),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'transport':'own_intake'}))
print(json.dumps({'visible':True,'complete':True,'evidence':str(evidence),'evidence_sha256':hashlib.sha256(evidence.read_bytes()).hexdigest()}))
"""
                    result, snapshot = run(owner, command(local, source_path, destination))
                    retain(owner, owner, json.loads(result['stdout']), snapshot)
                    if profile == 'state' and not shared:
                        marker = COMMON + "\npost_package(sys.argv[1], b'')\nprint(json.dumps({'transport': 'private_isolation_marker'}))\n"
                        run(owner, command(marker, batch))
                        writes.append({'owner': owner, 'batch': batch,
                                       'transport': 'private_isolation_marker'})
                        for actor in actors:
                            if actor == owner:
                                continue
                            destination = f'/workspace/received/{owner}/{batch}/{filename}'
                            reader = start(actor, command(STATE_RECEIVE,
                                urls[owner], owner, batch, destination))
                            received, snapshot = finish(actor, reader)
                            retain(owner, actor, received[0], snapshot)
                        continue
                    if profile == 'timing':
                        if shared:
                            sender = start(owner, command(ENDPOINT_TIMING, 'publish', source_path, batch))
                            sent, _ = finish(owner, sender)
                            metadata = sent[0]
                        else:
                            # Private isolation needs an actual service marker,
                            # not a retransmission of the owner's local source.
                            marker = COMMON + "\npost_package(sys.argv[1], b'')\nprint(json.dumps({'after': 0, 'transport': 'private_isolation_marker'}))\n"
                            result, _ = run(owner, command(marker, batch))
                            metadata = json.loads(result['stdout'])
                        writes.append({'owner': owner, 'batch': batch, **metadata})
                        for actor in actors:
                            if actor == owner:
                                continue
                            destination = f'/workspace/received/{owner}/{batch}/{filename}'
                            reader = start(actor, command(ENDPOINT_TIMING, 'receive',
                                urls[owner], metadata['after'], destination))
                            received, snapshot = finish(actor, reader)
                            retain(owner, actor, received[0], snapshot)
                        continue
                    readers = {}
                    for actor in actors:
                        if actor == owner:
                            continue
                        destination = f'/workspace/received/{owner}/{batch}/{filename}'
                        readers[actor] = start(actor, command(STATE_RECEIVE, urls[owner], owner, batch, destination))
                    ack_urls = [urls[a] for a in actors if shared and a != owner]
                    sender = start(owner, command(STATE_SEND, source_path, owner, batch, json.dumps(ack_urls)))
                    sent, _ = finish(owner, sender)
                    writes.append({'owner': owner, 'batch': batch, **sent[0]})
                    for actor, prefix in readers.items():
                        received, snapshot = finish(actor, prefix)
                        retain(owner, actor, received[0], snapshot)
            else:
                pending = {a: start(a, command(PUBLISH, profile, source_path, batch, 0, 0),
                                    settle=profile == 'timing') for a in actors}
                sent_by_owner = {owner: finish(owner, pending[owner])[0][0] for owner in actors}
                for owner, sent in sent_by_owner.items():
                    writes.append({'owner': owner, 'batch': batch, **sent})
                for actor in actors:
                    reads = []
                    for owner, sent in sent_by_owner.items():
                        # Coordinates only; neither source hash nor solution bytes.
                        wire = {k: sent[k] for k in ('name', 'offset', 'count', 'packed_bytes', 'after', 'events') if k in sent}
                        destination = f'/workspace/received/{owner}/{batch}/{filename}'
                        reads.append(command(RECEIVE, profile, urls[owner], json.dumps(wire), destination))
                    job = start(actor, 'set -e\n' + '\n'.join(reads))
                    received_rows, snapshot = finish(actor, job)
                    assert len(received_rows) == len(actors), received_rows
                    for owner, received in zip(actors, received_rows):
                        retain(owner, actor, received, snapshot)
            (output / 'transfers.json').write_text(json.dumps(transfers, indent=2) + '\n')
            (output / 'writes.json').write_text(json.dumps(writes, indent=2) + '\n')
            for actor in actors:
                run(actor, command(SOLVERS[domain].replace('/var/tmp/exports', '/workspace/received'),
                                   json.dumps(list(module.BATCHES[:stage + 1]))))
                run(actor, 'python tools/package_delivery.py ' + shlex.quote(batch))
        for actor in actors:
            snapshots[actor] = deployment.stations[actor].observe()
            (output / (actor + '-terminal.json')).write_text(json.dumps(snapshots[actor]) + '\n')
        bindings = deployment.bindings
    outcome = review_outcomes(domain, inputs, truth, snapshots, kind='worker_endpoint')
    (output / 'independent-outcome.json').write_text(json.dumps(outcome, indent=2) + '\n')
    assert all(value == shared for value in outcome['business_complete'].values()), outcome['business_complete']
    correct = sum(value for batches in outcome['delivered_complete'].values() for value in batches.values())
    assert correct == (9 if shared else 0), correct
    result = {'model_calls': 0, 'operator_authored': True, 'formation_assessed': False,
              'deployment': 'worker_endpoint', 'encoding': encoding, 'domain': domain,
              'shared': shared, 'input_sha256': digest(manifest), 'bindings': bindings,
              'correct_published_releases': correct, 'transfers': transfers,
              'foreign_transfers': sum(row['reader'] != row['owner'] for row in transfers),
              'private_foreign_visibility_checks': isolation_checks,
              'resources_closed': deployment.closed}
    (output / 'witness.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-key', default='november')
    parser.add_argument('--encoding', choices=('all', *ENCODINGS), default='all')
    parser.add_argument('--domain', choices=('all', *DOMAINS), default='all')
    parser.add_argument('--smoke', action='store_true',
                        help='Exercise one concrete --encoding/--domain using live shared and private services.')
    parser.add_argument('--business', action='store_true',
                        help='Complete all three intakes and independently review nine published deliveries.')
    parser.add_argument('--scope', choices=('both', 'shared', 'private'), default='both')
    parser.add_argument('--output', type=Path,
                        help='New external directory for --business; optional new JSON file otherwise.')
    args = parser.parse_args()
    domains = tuple(DOMAINS) if args.domain == 'all' else (args.domain,)
    encodings = tuple(ENCODINGS) if args.encoding == 'all' else (args.encoding,)
    if args.smoke and args.business:
        parser.error('Choose --smoke or --business')
    if (args.smoke or args.business) and (args.domain == 'all' or args.encoding == 'all'):
        parser.error('Live checks require one concrete --domain and --encoding')
    if args.business and not args.output:
        parser.error('--business requires --output')
    if args.output and (args.output.resolve().exists() or args.output.resolve().is_relative_to(ROOT)):
        parser.error('Choose a new output path outside the repository')
    if args.business:
        output = args.output.resolve()
        code = output / 'witness-code'
        code.mkdir(parents=True)
        hashes = {}
        for source in (Path(__file__), Path(__file__).with_name('swarmform_endpoint_witness_codecs.py'),
                       Path(__file__).with_name('swarmform_endpoint_timing_witness.py'),
                       Path(__file__).with_name('swarmform_service_timing_witness.py')):
            data = source.read_bytes()
            (code / source.name).write_bytes(data)
            hashes[source.name] = sha256(data).hexdigest()
        source_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        (output / 'source.json').write_text(json.dumps({'source_commit': source_commit,
            'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
            'witness_code_sha256': hashes,
            'timing_symbol_bits': ENDPOINT_TIMING_SYMBOL_BITS if args.encoding == 'timing' else None}, indent=2) + '\n')
        scopes = (True, False) if args.scope == 'both' else (args.scope == 'shared',)
        rows = [business(args.encoding, args.domain, shared, output / ('shared' if shared else 'private'),
                         args.dataset_key) for shared in scopes]
        report = {'deployment': 'worker_endpoint', 'encoding': args.encoding, 'domain': args.domain,
                  'model_calls': 0, 'source_commit': source_commit, 'results': rows}
        (output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'encoding': args.encoding, 'domain': args.domain, 'model_calls': 0,
                          'results': [{k: row[k] for k in ('shared', 'correct_published_releases', 'resources_closed')}
                                      for row in rows]}))
        return
    rows = catalog_check(args.dataset_key, domains, encodings)
    live = smoke(args.encoding, args.dataset_key, args.domain) if args.smoke else None
    report = {'kind': 'swarmform_worker_endpoint_input_witness',
              'model_calls': 0, 'formation_assessed': False,
              'dataset_key': args.dataset_key, 'input_cells': rows,
              'live_smoke': live}
    if args.output:
        output = args.output.resolve()
        if output.exists() or output.is_relative_to(ROOT):
            parser.error('Choose a new output file outside the repository')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'worker_endpoint_inputs': len(rows),
                      'encodings': sorted({row['encoding'] for row in rows}),
                      'domains': sorted({row['domain'] for row in rows}),
                      'live_smoke': live is not None, 'model_calls': 0}))


if __name__ == '__main__':
    main()
