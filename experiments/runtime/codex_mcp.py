"""Expose only the controller's currently registered tools to Codex over MCP."""

import json
from pathlib import Path
import socket
import sys


def tools(path):
    return json.loads(Path(path).read_text())


def serve(definitions, endpoint):
    for line in sys.stdin:
        request = json.loads(line)
        if 'id' not in request:
            continue
        method, params = request['method'], request.get('params') or {}
        response = {'jsonrpc': '2.0', 'id': request['id']}
        try:
            if method == 'initialize':
                response['result'] = {
                    'protocolVersion': params['protocolVersion'],
                    'capabilities': {'tools': {'listChanged': True}},
                    'serverInfo': {'name': 'work', 'version': '1.0'},
                }
            elif method == 'ping':
                response['result'] = {}
            elif method == 'tools/list':
                response['result'] = {'tools': tools(definitions)}
            elif method == 'tools/call':
                if params.get('name') not in {row['name'] for row in tools(definitions)}:
                    raise ValueError('Tool is not active')
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(300)
                    client.connect(endpoint)
                    with client.makefile('rwb') as stream:
                        stream.write((json.dumps(params) + '\n').encode())
                        stream.flush()
                        value = json.loads(stream.readline())
                if value.get('aborted'):
                    raise ValueError('Controller stopped this operation')
                response['result'] = {'content': [{'type': 'text', 'text': value['output']}],
                    'isError': False}
            else:
                response['error'] = {'code': -32601, 'message': 'Unsupported MCP method'}
        except (ValueError, OSError) as error:
            response['error'] = {'code': -32602, 'message': str(error)}
        print(json.dumps(response), flush=True)


if __name__ == '__main__':
    serve(*sys.argv[1:])
