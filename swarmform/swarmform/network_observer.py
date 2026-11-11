"""Extract complete scalar TCP and UNIX-stream operations from protected process observations."""
import base64
from hashlib import sha256
import re

PREFIX = re.compile(r'^(\d+)\s+(\d+\.\d+)\s+(.+)$')
CALL = re.compile(r'^(recvfrom|sendto|read|write)\((\d+)<(TCP|UNIX-STREAM):\[([^\]]+)\]>, "((?:\\x[0-9a-f]{2})*)", (\d+)(.*?)\) = (-?\d+)(?: .*)?$')


def unix_peer_annotations(text):
    """An early send can precede accept; bind it to this descriptor's later pair."""
    annotations, closes = {}, {}
    for number, line in enumerate(text.splitlines(), 1):
        prefix = PREFIX.fullmatch(line)
        if not prefix:
            continue
        pid, _, body = prefix.groups()
        for fd, inode, peer in re.findall(r'(\d+)<UNIX-STREAM:\[(\d+)->(\d+)', body):
            annotations.setdefault((int(pid), int(fd), inode), []).append((number, peer))
        close = re.match(r'close\((\d+)<UNIX-STREAM:\[(\d+)', body)
        if close:
            closes.setdefault((int(pid), int(close[1]), close[2]), []).append(number)
    return annotations, closes


def operations(text, *, actor, network_namespace):
    if not actor or not network_namespace:
        raise ValueError('Bind the process owner and network namespace')
    records, unresolved, pending = [], [], {}
    unix_pairs, unix_closes = unix_peer_annotations(text)
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
            if any(marker in body for marker in ('<TCP:', '<UNIX-STREAM:')) and body.startswith(('recvfrom(', 'sendto(', 'read(', 'write(', 'readv(', 'writev(', 'sendmsg(', 'recvmsg(', 'sendfile(')):
                if not re.search(r'\) = -1\b', body):
                    unresolved.append({'pid': pid, 'lines': source_lines, 'reason': 'unsupported or incomplete stream operation'})
            continue
        operation, fd, protocol, endpoints, encoded, requested, _, returned = match.groups()
        requested, returned = int(requested), int(returned)
        if returned < 0:
            continue
        data = bytes.fromhex(encoded.replace('\\x', ''))
        if returned > requested or len(data) < returned or (protocol == 'TCP' and endpoints.count('->') != 1):
            unresolved.append({'pid': pid, 'lines': source_lines, 'reason': 'incomplete bytes or socket endpoints'})
            continue
        data = data[:returned]
        address = {}
        if protocol == 'UNIX-STREAM':
            endpoint_match = re.fullmatch(r'(\d+)(?:->(\d+))?(?:,(@?)"((?:\\x[0-9a-f]{2})*)")?', endpoints)
            if not endpoint_match:
                unresolved.append({'pid': pid, 'lines': source_lines, 'reason': 'incomplete UNIX-stream endpoints'})
                continue
            local, peer, abstract, name = endpoint_match.groups()
            peer_lines = []
            if peer is None:
                key = (pid, int(fd), local)
                boundaries = unix_closes.get(key, [])
                lower = max((n for n in boundaries if n < source_lines[0]), default=0)
                upper = min((n for n in boundaries if n > source_lines[-1]), default=float('inf'))
                candidates = [(n, value) for n, value in unix_pairs.get(key, []) if lower < n < upper]
                peers = {value for _, value in candidates}
                if len(peers) != 1:
                    unresolved.append({'pid': pid, 'lines': source_lines, 'reason': 'UNIX-stream peer not observed in descriptor lifetime'})
                    continue
                peer = peers.pop()
                peer_lines = [n for n, value in candidates if value == peer]
            address = {'transport': 'unix_stream', 'local_inode': int(local), 'peer_inode': int(peer)}
            if peer_lines:
                address['peer_binding_lines'] = peer_lines
            if name is not None:
                address['socket_name_base64'] = base64.b64encode((b'\0' if abstract else b'') + bytes.fromhex(name.replace('\\x', ''))).decode()
            local, peer = 'unix:' + local, 'unix:' + peer
        else:
            local, peer = endpoints.split('->')
        records.append({'actor': actor, 'network_namespace': network_namespace, 'pid': pid,
                        'fd': int(fd), 'local': local, 'peer': peer, 'operation': operation,
                        'direction': 'receive' if operation in ('recvfrom', 'read') else 'send',
                        'began': began, 'completed': timestamp, 'lines': source_lines,
                        'transferred_bytes': returned, 'sha256': sha256(data).hexdigest(),
                        'content_base64': base64.b64encode(data).decode(), **address})
    unresolved.extend({**row, 'reason': 'unfinished at capture'} for row in pending.values()
                      if any(marker in row['body'] for marker in ('<TCP:', '<UNIX-STREAM:')))
    return {'operations': records, 'unresolved': unresolved,
            'scope': 'process TCP/UNIX-stream bytes; native inspection and downstream use are separate'}
