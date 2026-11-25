"""Recover store receipts when a wrapper consumes a mapped client's stdout."""
import hashlib
import json
import re

from swarmform.read_observer import trace_blocks

HEX_STRING = rb'"((?:\\x[0-9a-f]{2})*)"'
EXEC = re.compile(rb'\bexecve\(' + HEX_STRING + rb', \[([^\]]*)\]')
CLIENT_PATH = b'/workspace/projects.py'
ESCAPED_CLIENT = b''.join(b'\\x%02x' % byte for byte in CLIENT_PATH)
SOURCE_READ = re.compile(rb'\bread\(\d+<(?:' + re.escape(CLIENT_PATH) + b'|' + re.escape(ESCAPED_CLIENT)
                         + rb')>, ' + HEX_STRING + rb', \d+\)\s+= (\d+)')
STDOUT_WRITE = re.compile(rb'\bwrite\(1<[^>]+>, ' + HEX_STRING + rb', (\d+)\)\s+= (\d+)')


def unhex(data):
    return bytes.fromhex(data.replace(b'\\x', b'').decode())


def log_lines(archive, entry):
    tail = b''
    for block in trace_blocks(archive, entry):
        lines = (tail + block).split(b'\n')
        tail = lines.pop()
        yield from lines
    if tail:
        yield tail


def client_launch(line):
    match = EXEC.search(line)
    if not match or not re.fullmatch(rb'(?:.*/)?python(?:3(?:\.\d+)?)?', unhex(match[1])):
        return None
    argv = [unhex(arg) for arg in re.findall(HEX_STRING, match[2])]
    if len(argv) < 4 or argv[1] not in (b'projects.py', CLIENT_PATH) or argv[2] not in (b'read', b'write'):
        return None
    return argv[2].decode(), argv[3].decode(errors='surrogateescape')


def client_receipts(archive, log, source_hash, keys):
    pending, running, verified = {}, {}, set()
    for number, line in enumerate(log_lines(archive, log), 1):
        parts = line.split(None, 2)
        if len(parts) != 3 or not parts[0].isdigit():
            continue
        pid = parts[0]
        if parts[2].startswith(b'+++') or b'+++ exited' in line[:125] or b'+++ killed' in line[:125]:
            pending.pop(pid, None)
            running.pop(pid, None)
            verified.discard(pid)
            continue
        if b'execve(' in line[:110]:
            running.pop(pid, None)
            pending.pop(pid, None)
            verified.discard(pid)
            launch = client_launch(line)
            if launch and line.endswith(b'= 0'):
                running[pid] = (*launch, number)
            elif launch and b'<unfinished ...>' in line:
                pending[pid] = (*launch, number)
        elif b'execve resumed>' in line[:110]:
            launch = pending.pop(pid, None)
            if launch and line.endswith(b'= 0'):
                running[pid] = launch
        elif pid in running and b'read(' in line[:110]:
            if CLIENT_PATH not in line[:240] and ESCAPED_CLIENT not in line[:240]:
                continue
            match = SOURCE_READ.search(line)
            if match and len(match[1]) == 4 * int(match[2]) and hashlib.sha256(unhex(match[1])).digest() == source_hash:
                verified.add(pid)
        elif pid in verified and b'write(1<' in line[:110]:
            match = STDOUT_WRITE.search(line)
            if not match or match[2] != match[3] or len(match[1]) != 4 * int(match[3]):
                continue
            try:
                value = json.loads(unhex(match[1]))
            except (UnicodeError, ValueError):
                continue
            if not isinstance(value, dict):
                continue
            operation, name, launch_line = running[pid]
            version, digest = value.get('version'), value.get('sha256')
            if value.get('name') != name or not isinstance(version, int) or not isinstance(digest, str):
                continue
            if (name, version, digest) not in keys:
                continue
            if ('text' in value or 'saved_to' in value) != (operation == 'read'):
                continue
            yield float(parts[1]), dict(operation=operation, name=name, version=version, sha256=digest,
                                        exec_line=launch_line, receipt_line=number)


def observed_operations(case, keys, origin, deadline):
    if not keys or not isinstance(deadline, (int, float)) or not (case / 'inputs.json').is_file():
        return []
    openings = json.loads((case / 'inputs.json').read_bytes()).get('startup', {})
    results = []
    for actor, files in openings.items():
        client = files.get(CLIENT_PATH.decode())
        archive = case / 'reads' / actor
        indexes = sorted(archive.glob('[0-9]*.json'))
        origins = archive / 'origins.json'
        if not isinstance(client, str) or not indexes or not origins.is_file():
            continue
        source_hash = hashlib.sha256(client.encode()).digest()
        bindings = json.loads(origins.read_bytes())
        logs = json.loads(indexes[-1].read_bytes())['files']
        for name, log in logs.items():
            call = bindings.get(name, {}).get('native_call') or {}
            if call.get('actor') != actor or not call.get('call_id'):
                continue
            for timestamp, record in client_receipts(archive, log, source_hash, keys):
                seconds = timestamp - origin
                if 0 <= seconds < deadline:
                    results.append(dict(actor=actor, seconds=seconds, call_id=call['call_id'], trace_file=name, **record))
    return results
