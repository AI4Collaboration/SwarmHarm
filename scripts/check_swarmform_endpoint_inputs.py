#!/usr/bin/env python3
"""Build worker-endpoint inputs and optionally exercise one live view."""

import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import shlex
import sys
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'experiments/runtime'),
                str(ROOT / 'experiments/swarmharm-v1')]

from swarmform.domain_inputs import DOMAINS
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-key', default='november')
    parser.add_argument('--encoding', choices=('all', *ENCODINGS), default='all')
    parser.add_argument('--domain', choices=('all', *DOMAINS), default='all')
    parser.add_argument('--smoke', action='store_true',
                        help='Exercise one concrete --encoding/--domain using live shared and private services.')
    parser.add_argument('--output', type=Path,
                        help='Optional new JSON report path outside the repository.')
    args = parser.parse_args()
    domains = tuple(DOMAINS) if args.domain == 'all' else (args.domain,)
    encodings = tuple(ENCODINGS) if args.encoding == 'all' else (args.encoding,)
    if args.smoke and (args.domain == 'all' or args.encoding == 'all'):
        parser.error('--smoke requires one concrete --domain and --encoding')
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
