"""Send and retrieve the office's delivery copies."""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


def request(method, path, value=None):
    config = json.loads(Path('/workspace/processor.json').read_text())
    body = json.dumps(value).encode() if value is not None else None
    call = Request(config['url'] + path, data=body, method=method,
                   headers={'Content-Type': 'application/json', 'Authorization':'Bearer '+config['client_token']})
    with urlopen(call, timeout=20) as response:
        return json.load(response)


def submit(path, batch):
    data = Path(path).read_bytes()
    return request('POST', '/deliveries', {'batch': batch,
        'sha256': sha256(data).hexdigest(), 'content_base64': base64.b64encode(data).decode()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List delivery copies')
    get = commands.add_parser('get', help='Download a delivery copy')
    get.add_argument('name')
    get.add_argument('output', type=Path)
    describe=commands.add_parser('describe',help='Update delivery notes')
    describe.add_argument('name')
    describe.add_argument('notes_file',type=Path)
    state=commands.add_parser('state',help='Update delivery status');state.add_argument('name');state.add_argument('value',choices=('draft','ready','archived'))
    copies=commands.add_parser('copy-batch',help='Prepare draft delivery copies');copies.add_argument('source');copies.add_argument('names_file',type=Path)
    states=commands.add_parser('state-batch',help='Update a list of delivery statuses');states.add_argument('changes_file',type=Path)
    args = parser.parse_args()
    if args.command == 'list':
        result = request('GET', '/deliveries')
    elif args.command == 'describe':
        result=request('PATCH','/deliveries/'+quote(args.name,safe=''),{'notes':args.notes_file.read_text()})
    elif args.command=='state':result=request('PATCH','/deliveries/'+quote(args.name,safe=''),{'state':args.value})
    elif args.command=='copy-batch':result=request('POST','/copies/batch',{'source':args.source,'names':json.loads(args.names_file.read_text())})
    elif args.command=='state-batch':result=request('POST','/states/batch',{'changes':json.loads(args.changes_file.read_text())})
    else:
        result = request('GET', '/deliveries/' + quote(args.name, safe=''))
        data = base64.b64decode(result.pop('content_base64'), validate=True)
        if sha256(data).hexdigest() != result['sha256']:
            raise ValueError('Downloaded copy differs from its digest')
        args.output.write_bytes(data)
    print(json.dumps(result))
