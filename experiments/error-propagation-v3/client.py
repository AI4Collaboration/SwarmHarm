"""Office command-line client."""
import argparse
import json
import sys
from urllib.request import Request, urlopen


parser = argparse.ArgumentParser(description='Office records, working notes and settlements.')
parser.add_argument('op', choices=['overview', 'records', 'ledger', 'inbox', 'post', 'reverse', 'note', 'summary'])
for name in ('item', 'payment', 'memo', 'to', 'text'): parser.add_argument('--' + name)
parser.add_argument('--cents', type=int)
args = vars(parser.parse_args()); op = args.pop('op')
request = Request('http://127.0.0.1:8123', json.dumps({'op': op, 'args': args}).encode(), {'Content-Type': 'application/json'})
with urlopen(request, timeout=30) as response:
    result = json.loads(response.read())
if isinstance(result, dict) and 'error' in result:
    print(json.dumps(result), file=sys.stderr); sys.exit(2)
print(json.dumps(result))
