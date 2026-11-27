"""Recover store receipts when a wrapper consumes a mapped client's stdout."""
import hashlib
import json
import re
from pathlib import PurePosixPath

from swarmform.read_observer import trace_blocks

HEX_STRING = rb'"((?:\\x[0-9a-f]{2})*)"'
EXEC = re.compile(rb'\bexecve\(' + HEX_STRING + rb', \[([^\]]*)\]')
CLIENT_PATH = b'/workspace/projects.py'
ESCAPED_CLIENT = b''.join(b'\\x%02x' % byte for byte in CLIENT_PATH)
SOURCE_READ = re.compile(rb'\bread\(\d+<(?:' + re.escape(CLIENT_PATH) + b'|' + re.escape(ESCAPED_CLIENT)
                         + rb')>, ' + HEX_STRING + rb', \d+\)\s+= (\d+)')
# strace prints a character device as 1</dev/null<char 1:3>>.
STDOUT_WRITE = re.compile(rb'\bwrite\(1<(?:[^>]+>|[^<>]+<char \d+:\d+>>), ' + HEX_STRING + rb', (\d+)\)\s+= (\d+)')


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


def client_launch(line, checkout=False, work=False, save=False):
    match = EXEC.search(line)
    if not match or not re.fullmatch(rb'(?:.*/)?python(?:3(?:\.\d+)?)?', unhex(match[1])):
        return None
    argv = [unhex(arg) for arg in re.findall(HEX_STRING, match[2])]
    if work and len(argv) >= 6 and argv[1] in (b'projects.py', CLIENT_PATH) and argv[2] == b'work' and b'--' in argv[3:]:
        names = argv[3:argv.index(b'--',3)]
        return 'work', frozenset(name.decode(errors='surrogateescape') for name in names)
    if save and len(argv) >= 5 and argv[1] in (b'projects.py', CLIENT_PATH) and argv[2] == b'save':
        names = tuple(arg.decode(errors='surrogateescape') for arg in argv[4:] if arg != b'--')
        if not names or len(names) != len(set(names)) or any(
                not name or name.startswith(('/', '-')) or '\\' in name or '\0' in name
                or any(part in ('', '.', '..') for part in name.split('/')) for name in names):
            return None
        return 'save', names
    operations = (b'read', b'write', b'checkout') if checkout else (b'read', b'write')
    if len(argv) < 4 or argv[1] not in (b'projects.py', CLIENT_PATH) or argv[2] not in operations:
        return None
    return argv[2].decode(), argv[3].decode(errors='surrogateescape')


def client_receipts(archive, log, source_hash, keys, checkout=False, work=False, save=False):
    pending, running, verified = {}, {}, set()
    unfinished_io = {}
    for number, line in enumerate(log_lines(archive, log), 1):
        parts = line.split(None, 2)
        if len(parts) != 3 or not parts[0].isdigit():
            continue
        pid = parts[0]
        # strace can print one read or write on two lines when clients run concurrently.
        # Attribute it at completion and keep the original trace line number for replay.
        if pid in running:
            if line.endswith(b' <unfinished ...>'):
                if b'read(' in line[:110] and (CLIENT_PATH in line[:240] or ESCAPED_CLIENT in line[:240]):
                    unfinished_io[pid] = (b'<... read resumed>', line[:-len(b' <unfinished ...>')])
                elif pid in verified and b'write(1<' in line[:110]:
                    unfinished_io[pid] = (b'<... write resumed>', line[:-len(b' <unfinished ...>')])
            elif pid in unfinished_io and b' resumed>' in line[:110]:
                marker, start = unfinished_io.pop(pid)
                if marker in line[:110]:
                    line = start + line.split(marker, 1)[1]
        if parts[2].startswith(b'+++') or b'+++ exited' in line[:125] or b'+++ killed' in line[:125]:
            unfinished_io.pop(pid, None)
            pending.pop(pid, None)
            running.pop(pid, None)
            verified.discard(pid)
            continue
        if b'execve(' in line[:110]:
            unfinished_io.pop(pid, None)
            running.pop(pid, None)
            pending.pop(pid, None)
            verified.discard(pid)
            launch = client_launch(line, checkout, work, save)
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
            if operation == 'save':
                selected, name = name, value.get('name')
                if name not in selected or set(value) != {'name','version','bytes','sha256'}:
                    continue
                operation = 'write'
            elif operation == 'checkout':
                # The verified batch client prints one saved_to acknowledgment per pinned read.
                directory, name = name, value.get('name')
                if not isinstance(name, str) or value.get('saved_to') != str(PurePosixPath(directory) / name):
                    continue
                operation = 'read'
            elif operation == 'work':
                selected, name = name, value.get('name')
                saved = value.get('saved_to')
                if name not in selected or not isinstance(saved, str):
                    continue
                target = PurePosixPath(saved)
                relative = PurePosixPath(name)
                if not target.is_absolute() or len(target.parts) <= len(relative.parts):
                    continue
                directory = target.parents[len(relative.parts)-1]
                if not directory.name.startswith('project-work-') or directory / relative != target:
                    continue
                operation = 'read'
            version, digest = value.get('version'), value.get('sha256')
            if value.get('name') != name or not isinstance(version, int) or not isinstance(digest, str):
                continue
            if (name, version, digest) not in keys:
                continue
            if ('text' in value or 'saved_to' in value) != (operation == 'read'):
                continue
            if running[pid][0] == 'save':
                running[pid] = ('save', selected[selected.index(name)+1:], launch_line)
            yield float(parts[1]), dict(operation=operation, name=name, version=version, sha256=digest,
                                        exec_line=launch_line, receipt_line=number,
                                        **({'saved_to': value['saved_to']} if 'saved_to' in value else {}))


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
        checkout = 'def mapped_checkout_call(arguments):' in client
        work = 'receipt = mapped_checkout_call(["read",' in client
        save = 'def mapped_save_call(arguments):' in client
        bindings = json.loads(origins.read_bytes())
        logs = json.loads(indexes[-1].read_bytes())['files']
        for name, log in logs.items():
            call = bindings.get(name, {}).get('native_call') or {}
            if call.get('actor') != actor or not call.get('call_id'):
                continue
            for timestamp, record in client_receipts(archive, log, source_hash, keys, checkout, work, save):
                seconds = timestamp - origin
                if 0 <= seconds < deadline:
                    results.append(dict(actor=actor, seconds=seconds, call_id=call['call_id'], trace_file=name, **record))
    return results
