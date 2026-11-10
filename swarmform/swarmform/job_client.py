"""Submit report bundles, inspect processing history and retrieve results."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def request(method, path, value=None):
    config = json.loads(Path('/workspace/processing.json').read_text())
    body = json.dumps(value).encode() if value is not None else None
    call = Request(config['url'] + path, data=body, method=method,
                   headers={'Authorization': 'Bearer ' + config['key'], 'Content-Type': 'application/json'})
    try:
        with urlopen(call, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        if __name__ != '__main__':
            raise
        detail = error.read().decode('utf-8', errors='replace')
        raise SystemExit(f"HTTP {error.code}: {detail or error.reason}") from None


def submit(path, name=None, metadata=None):
    path = Path(path)
    return request('POST', '/jobs', {'name': name or path.name, 'metadata': metadata or {},
                                    'content_base64': base64.b64encode(path.read_bytes()).decode()})


def result(identifier, destination):
    value = request('GET', '/result?' + urlencode({'id': identifier}))
    content = base64.b64decode(value.pop('content_base64'), validate=True)
    if sha256(content).hexdigest() != value['sha256']:
        raise ValueError('Result differs from its digest')
    Path(destination).write_bytes(content)
    return value


def wait(identifier, timeout=60):
    deadline = time.monotonic() + timeout
    while True:
        rows = request('GET', '/jobs?' + urlencode({'after': identifier - 1}))['jobs']
        value = next((row for row in rows if row['id'] == identifier), None)
        if value and value['state'] in ('completed', 'failed', 'cancelled'):
            return value
        if time.monotonic() > deadline:
            raise TimeoutError('Processing is still pending')
        time.sleep(.1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='List processing jobs')
    listing.add_argument('--after', type=int, default=0)
    listing.add_argument('--match', type=json.loads, default={})
    upload = commands.add_parser('submit', help='Submit a ZIP bundle for processing')
    upload.add_argument('file')
    upload.add_argument('--name')
    upload.add_argument('--metadata', type=json.loads, default={})
    download = commands.add_parser('get', help='Download a completed result')
    download.add_argument('id', type=int)
    download.add_argument('output')
    cancel = commands.add_parser('cancel', help='Cancel a processing job')
    cancel.add_argument('id', type=int)
    events = commands.add_parser('events', help='Read retained processing events')
    events.add_argument('--after', type=int, default=0)
    batch = commands.add_parser('submit-batch', help='Submit a JSON list of job bundles')
    batch.add_argument('file')
    cancel_many = commands.add_parser('cancel-batch', help='Cancel a JSON list of job IDs')
    cancel_many.add_argument('file')
    retry_many = commands.add_parser('retry-batch', help='Retry failed or cancelled job IDs from a JSON list')
    retry_many.add_argument('file')
    args = parser.parse_args()
    if args.command == 'list':
        value = request('GET', '/jobs?' + urlencode({'after': args.after, 'match': json.dumps(args.match)}))
    elif args.command == 'submit':
        value = submit(args.file, args.name, args.metadata)
    elif args.command == 'get':
        value = result(args.id, args.output)
    elif args.command == 'cancel':
        value = request('POST', '/cancel', {'id': args.id})
    elif args.command == 'submit-batch':
        value = request('POST', '/jobs-batch', {'jobs': json.loads(Path(args.file).read_text())})
    elif args.command == 'cancel-batch':
        value = request('POST', '/cancel-batch', {'jobs': [{'id':i} for i in json.loads(Path(args.file).read_text())]})
    elif args.command == 'retry-batch':
        value = request('POST', '/retry-batch', {'jobs': [{'id':i} for i in json.loads(Path(args.file).read_text())]})
    else:
        value = request('GET', '/events?' + urlencode({'after': args.after}))
    print(json.dumps(value))
