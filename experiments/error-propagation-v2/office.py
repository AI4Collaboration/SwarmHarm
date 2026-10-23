"""Small local settlement office. Public records contain no verifier answers."""
import argparse
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen
import tempfile

STATE = Path('/var/lib/office/state.json')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, allow_nan=False); f.flush(); os.fsync(f.fileno())
    os.replace(name, path)
    fd = os.open(path.parent, os.O_RDONLY)
    os.fsync(fd); os.close(fd)


def operate(state, op, args):
    if op == 'records': return state['records']
    if op == 'ledger': return state['ledger']
    if op == 'overview':
        return {'company': state['company'], 'wave': state['wave'], 'queue': state['queue'],
                'commands': ['office records', 'office ledger', 'office inbox',
                  'office post --item ID --cents INTEGER --memo TEXT',
                  'office reverse --payment ID --cents INTEGER --memo TEXT',
                  'office note --to NAME --text TEXT', 'office summary --text TEXT']}
    if op == 'inbox':
        return {'notes': state['notes'], 'summaries': state['summaries']}
    if op == 'post':
        amount = args.get('cents')
        if type(amount) is not int or amount <= 0: raise ValueError('cents must be a positive integer')
        if args.get('item') not in state['queue']: raise ValueError('item is not in this queue')
        row = {'id': 'PAY-' + str(len(state['ledger']) + 1), 'item': args['item'],
               'cents': amount, 'kind': 'payment', 'memo': args.get('memo', ''), 'wave': state['wave']}
        state['ledger'].append(row); return row
    if op == 'reverse':
        amount = args.get('cents')
        row = next((p for p in state['ledger'] if p['id'] == args.get('payment') and p['kind'] == 'payment'), None)
        if row is None: raise ValueError('payment not found')
        reversed_cents = -sum(p['cents'] for p in state['ledger'] if p.get('payment') == row['id'])
        if type(amount) is not int or not 0 < amount <= row['cents'] - reversed_cents:
            raise ValueError('reversal exceeds remaining payment or is not positive integer cents')
        result = {'id': 'REV-' + str(len(state['ledger']) + 1), 'item': row['item'], 'cents': -amount,
                  'kind': 'reversal', 'payment': row['id'], 'memo': args.get('memo', ''), 'wave': state['wave']}
        state['ledger'].append(result); return result
    if op in ('note', 'summary'):
        text = args.get('text')
        if not isinstance(text, str) or not text.strip() or len(text) > 12000: raise ValueError('text must contain 1 to 12000 characters')
        row = {'wave': state['wave'], 'text': text}
        if op == 'note': row['to'] = args.get('to', 'office')
        state['notes' if op == 'note' else 'summaries'].append(row); return row
    raise ValueError('unknown command')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_POST(self):
        try:
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state = json.loads(STATE.read_text())
            try:
                result = operate(state, request['op'], request.get('args', {})); status = 'ok'
            except (ValueError, KeyError, TypeError) as e:
                result = {'error': str(e)}; status = 'error'
            state['audit'].append({'seq': len(state['audit']) + 1, 'wave': state['wave'],
                                   'request': request, 'status': status, 'result': result})
            save(STATE, state)
            body = json.dumps(result).encode(); self.send_response(200)
        except Exception as e:
            body = json.dumps({'error': type(e).__name__}).encode(); self.send_response(500)
        self.end_headers(); self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('op', choices=['serve', 'overview', 'records', 'ledger', 'inbox', 'post', 'reverse', 'note', 'summary'])
    for name in ('item', 'payment', 'memo', 'to', 'text'): parser.add_argument('--' + name)
    parser.add_argument('--cents', type=int)
    args = vars(parser.parse_args()); op = args.pop('op')
    if op == 'serve':
        if not STATE.exists(): save(STATE, json.loads(Path('/opt/office/seed.json').read_text()))
        HTTPServer(('127.0.0.1', 8123), Handler).serve_forever()
    else:
        request = Request('http://127.0.0.1:8123', json.dumps({'op': op, 'args': args}).encode(), {'Content-Type': 'application/json'})
        with urlopen(request, timeout=30) as response: print(response.read().decode())


if __name__ == '__main__': main()
