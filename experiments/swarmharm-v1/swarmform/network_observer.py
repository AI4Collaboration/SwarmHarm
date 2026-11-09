"""Extract complete scalar TCP operations from protected process observations."""
import base64
from hashlib import sha256
import re

PREFIX = re.compile(r'^(\d+)\s+(\d+\.\d+)\s+(.+)$')
CALL = re.compile(r'^(recvfrom|sendto|read|write)\((\d+)<TCP:\[([^\]]+)\]>, "((?:\\x[0-9a-f]{2})*)", (\d+)(.*?)\) = (-?\d+)(?: .*)?$')


def operations(text, *, actor, network_namespace):
    if not actor or not network_namespace:
        raise ValueError('Bind the process owner and network namespace')
    records, unresolved, pending = [], [], {}
    for number, line in enumerate(text.splitlines(), 1):
        prefix = PREFIX.fullmatch(line)
        if not prefix:
            continue
        pid, timestamp, body = prefix.groups()
        pid, source_lines = int(pid), [number]
        began = timestamp
        if body.endswith(' <unfinished ...>'):
            if body.startswith(('recvfrom(', 'sendto(', 'read(', 'write(')):
                if pid in pending:
                    unresolved.append({**pending[pid], 'reason': 'another unfinished operation'})
                pending[pid] = {'pid': pid, 'lines': source_lines, 'began': began,
                                'body': body[:-len(' <unfinished ...>')]}
            continue
        resumed = re.fullmatch(r'<\.\.\. (recvfrom|sendto|read|write) resumed>(.*)', body)
        if resumed:
            start = pending.pop(pid, None)
            if start is None or not start['body'].startswith(resumed[1] + '('):
                unresolved.append({'pid': pid, 'lines': source_lines, 'reason': 'unmatched resume'})
                continue
            body = start['body'] + resumed[2]
            source_lines, began = start['lines'] + source_lines, start['began']
        match = CALL.fullmatch(body)
        if not match:
            if '<TCP:' in body and body.startswith(('recvfrom(', 'sendto(', 'read(', 'write(', 'readv(', 'writev(', 'sendmsg(', 'recvmsg(', 'sendfile(')):
                if not re.search(r'\) = -1\b', body):
                    unresolved.append({'pid': pid, 'lines': source_lines, 'reason': 'unsupported or incomplete TCP operation'})
            continue
        operation, fd, endpoints, encoded, requested, _, returned = match.groups()
        requested, returned = int(requested), int(returned)
        if returned < 0:
            continue
        data = bytes.fromhex(encoded.replace('\\x', ''))
        if returned > requested or len(data) < returned or endpoints.count('->') != 1:
            unresolved.append({'pid': pid, 'lines': source_lines, 'reason': 'incomplete bytes or socket endpoints'})
            continue
        data = data[:returned]
        local, peer = endpoints.split('->')
        records.append({'actor': actor, 'network_namespace': network_namespace, 'pid': pid,
                        'fd': int(fd), 'local': local, 'peer': peer, 'operation': operation,
                        'direction': 'receive' if operation in ('recvfrom', 'read') else 'send',
                        'began': began, 'completed': timestamp, 'lines': source_lines,
                        'transferred_bytes': returned, 'sha256': sha256(data).hexdigest(),
                        'content_base64': base64.b64encode(data).decode()})
    unresolved.extend({**row, 'reason': 'unfinished at capture'} for row in pending.values()
                      if '<TCP:' in row['body'])
    return {'operations': records, 'unresolved': unresolved,
            'scope': 'process TCP bytes; native inspection and downstream use are separate'}
