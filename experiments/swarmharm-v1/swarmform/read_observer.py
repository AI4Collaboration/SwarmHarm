"""Protected command observations for the actual file-volume fixture."""

import base64
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

from atomic import atomic_json
from swarmform.file_deployment import FileStation

TRACE_ROOT = '/var/log/workstation'
READ_LOGS = r'''
import base64,json,os
from pathlib import Path
root=Path('/var/log/workstation')
opened=set()
for process in Path('/proc').iterdir():
    if not process.name.isdigit():continue
    try:
        for fd in (process/'fd').iterdir():
            try:opened.add(os.readlink(fd))
            except OSError:pass
    except OSError:pass
files={p.name:base64.b64encode(p.read_bytes()).decode() for p in root.iterdir() if p.is_file()}
print(json.dumps({'files':files,'closed':[name for name in files if str(root/name) not in opened]}))
'''
PRUNE_LOGS = r'''
import hashlib,json
from pathlib import Path
for name,digest in json.load(__import__('sys').stdin).items():
    if Path(name).name!=name:raise ValueError('Invalid observation filename')
    p=Path('/var/log/workstation')/name
    if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise ValueError('Closed observation changed')
    p.unlink()
'''


def observed_reads(log):
    """Extract complete scalar reads only; path presence alone never earns a read."""
    pattern = re.compile(r'^(\d+)\s+(\d+\.\d+)\s+(read|pread64)\(\d+<([^>]+)>, "((?:\\x[0-9a-f]{2})*)", (\d+)(?:, (\d+))?\) = (\d+)$')
    reads = []
    for number, line in enumerate(log.splitlines(), 1):
        match = pattern.fullmatch(line)
        if not match:
            continue
        pid, timestamp, operation, raw_path, raw_bytes, requested, offset, returned = match.groups()
        path = re.sub(r'\\x([0-9a-f]{2})', lambda m: chr(int(m[1], 16)), raw_path)
        data = bytes.fromhex(raw_bytes.replace('\\x', ''))
        if not path.startswith(('/workspace/', '/var/tmp/exports/', '/tmp/')) or len(data) != int(returned):
            continue
        reads.append({'line': number, 'pid': int(pid), 'at_unix': timestamp, 'operation': operation,
                      'path': path, 'requested_bytes': int(requested), 'returned_bytes': len(data),
                      'explicit_offset': int(offset) if offset is not None else None,
                      'data_base64': base64.b64encode(data).decode(), 'sha256': sha256(data).hexdigest()})
    return reads


class ObservedFileStation(FileStation):
    """The observer retains process reads; native traces still establish model exposure."""

    def __init__(self, initial_files, *, archive, **kwargs):
        self.archive = Path(archive).resolve()
        repo = Path(__file__).resolve().parents[3]
        if self.archive.is_relative_to(repo) or self.archive.exists():
            raise ValueError('Choose a new observation directory outside the repository')
        self.archive.mkdir(parents=True)
        self.command_count = self.capture_count = 0
        self.previous = {}
        self.pruned = set()
        super().__init__(initial_files, trace_commands=True, **kwargs)
        try:
            self.observer_version = subprocess.check_output(
                ['docker', 'exec', self.name, 'strace', '--version'], text=True, timeout=10).splitlines()[0]
        except BaseException:
            self.close()
            raise

    def command_argv(self, command):
        self.command_count += 1
        return ['docker', 'exec', '--user', '0:0', '--workdir', '/workspace', self.name,
                'strace', '-DDD', '-f', '-ttt', '-yy', '-s', '262144', '-xx',
                '-e', 'trace=%file,%desc,%process,%memory',
                '-o', f'{TRACE_ROOT}/{self.command_count:06d}.log', '-u', '65534:65534',
                'timeout', '--kill-after=1s', '30s', 'bash', '-lc', command]

    def retain_traces(self):
        observed = json.loads(subprocess.check_output(
            ['docker', 'exec', '--user', '0:0', self.name, 'python', '-I', '-c', READ_LOGS], timeout=30))
        logs = observed['files']
        if set(self.previous) - set(logs) - self.pruned:
            raise RuntimeError('An unarchived command observation disappeared')
        if set(logs) & self.pruned:
            raise RuntimeError('A closed command observation was reopened')
        files = {}
        blobs = self.archive/'blobs'
        blobs.mkdir(exist_ok=True)
        active_bytes = 0
        for name, encoded in logs.items():
            data = base64.b64decode(encoded, validate=True)
            prior = self.previous.get(name, b'')
            if not data.startswith(prior):
                raise RuntimeError('Command observation is no longer append-only')
            digest = sha256(data).hexdigest()
            destination = blobs/digest
            if not destination.exists():
                with destination.open('xb') as handle:
                    handle.write(data)
            self.previous[name] = data
            if name not in observed['closed']:
                active_bytes += len(data)
        for name, data in self.previous.items():
            digest = sha256(data).hexdigest()
            files[name] = {'bytes': len(data), 'sha256': digest, 'blob': f'blobs/{digest}'}
        if active_bytes > 96_000_000:
            raise RuntimeError('Command observation reached its registered storage allowance')
        self.capture_count += 1
        record = {'commands_started': self.command_count, 'observer': getattr(self, 'observer_version', None),
                  'files': files, 'claim_scope': 'process_operations_not_model_comprehension'}
        path = self.archive/f'{self.capture_count:06d}.json'
        atomic_json(path, record)
        closed = {name: files[name]['sha256'] for name in observed['closed']}
        if closed:
            subprocess.run(['docker', 'exec', '-i', '--user', '0:0', self.name, 'python', '-I', '-c', PRUNE_LOGS],
                           input=json.dumps(closed), text=True, capture_output=True, check=True, timeout=30)
            self.pruned.update(closed)
        return {'path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()}

    def execute(self, command, shared):
        result, snapshot = super().execute(command, shared)
        snapshot['command_observation'] = self.retain_traces()
        return result, snapshot

    def close(self):
        if not self.closed:
            try:
                # Capture before removal. Background operations are retained as
                # still in flight; this does not assert their later completion.
                if self.initialized:
                    self.capture_frozen('before_terminal_observation')
                    self.retain_traces()
            finally:
                super().close()
