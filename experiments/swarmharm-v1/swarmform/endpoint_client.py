"""Send and retrieve the office's delivery copies."""
import argparse
import base64
from hashlib import sha256
import json
import socket
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


def request(method, path, value=None, *, url=None):
    config = json.loads(Path('/workspace/processor.json').read_text())
    body = json.dumps(value).encode() if value is not None else None
    target = config['url'] if url is None else url.rstrip('/')
    headers = {'Content-Type': 'application/json'}
    if url is None or target == config['url'].rstrip('/'):
        headers['Authorization'] = 'Bearer ' + config['client_token']
    call = Request(target + path, data=body, method=method, headers=headers)
    try:
        with urlopen(call, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        if __name__ != '__main__':
            raise
        detail = error.read().decode('utf-8', errors='replace')
        raise SystemExit(f"HTTP {error.code}: {detail or error.reason}") from None


def submit(path, batch):
    data = Path(path).read_bytes()
    return request('POST', '/deliveries', {'batch': batch,
        'sha256': sha256(data).hexdigest(), 'content_base64': base64.b64encode(data).decode()})


def processor_status():
    connection = json.loads(Path('/workspace/processor.json').read_text())
    listeners = []
    for line in Path('/proc/net/tcp').read_text().splitlines()[1:]:
        fields = line.split()
        if fields[3] == '0A':
            address, port = fields[1].split(':')
            listeners.append({'address': socket.inet_ntoa(bytes.fromhex(address)[::-1]),
                              'port': int(port, 16)})
    return {'processor': connection['url'], 'tcp_listeners': sorted(listeners, key=lambda row: (row['address'], row['port']))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='List delivery copies')
    listing.add_argument('--url', metavar='URL', help='Processor base URL; defaults to processor.json')
    commands.add_parser('status', help='Show processor connection and local listener status')
    activity = commands.add_parser('activity', help='Read processor activity')
    activity.add_argument('--url', metavar='URL', help='Processor base URL; defaults to processor.json')
    activity.add_argument('--after', type=int, default=0)
    activity.add_argument('--limit', type=int, default=1024)
    get = commands.add_parser('get', help='Download a delivery copy')
    get.add_argument('--url', metavar='URL', help='Processor base URL; defaults to processor.json')
    get.add_argument('name')
    get.add_argument('output', type=Path)
    describe=commands.add_parser('describe',help='Update delivery notes')
    describe.add_argument('name')
    describe.add_argument('notes_file',type=Path)
    state=commands.add_parser('state',help='Update delivery status');state.add_argument('name');state.add_argument('value',choices=('draft','ready','archived'))
    copies=commands.add_parser('copy-batch',help='Prepare draft delivery copies');copies.add_argument('source');copies.add_argument('names_file',type=Path)
    states=commands.add_parser('state-batch',help='Update a list of delivery statuses');states.add_argument('changes_file',type=Path)
    args = parser.parse_args()
    if args.command == 'status':
        result = processor_status()
    elif args.command == 'list':
        result = request('GET', '/deliveries', url=args.url)
    elif args.command == 'activity':
        result = request('GET', '/activity?after=' + str(args.after) + '&limit=' + str(args.limit), url=args.url)
    elif args.command == 'describe':
        result=request('PATCH','/deliveries/'+quote(args.name,safe=''),{'notes':args.notes_file.read_text()})
    elif args.command=='state':result=request('PATCH','/deliveries/'+quote(args.name,safe=''),{'state':args.value})
    elif args.command=='copy-batch':result=request('POST','/copies/batch',{'source':args.source,'names':json.loads(args.names_file.read_text())})
    elif args.command=='state-batch':result=request('POST','/states/batch',{'changes':json.loads(args.changes_file.read_text())})
    else:
        result = request('GET', '/deliveries/' + quote(args.name, safe=''), url=args.url)
        data = base64.b64decode(result.pop('content_base64'), validate=True)
        if sha256(data).hexdigest() != result['sha256']:
            raise ValueError('Downloaded copy differs from its digest')
        args.output.write_bytes(data)
    print(json.dumps(result))
