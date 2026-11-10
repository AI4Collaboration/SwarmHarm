"""Opt-in continuation on actual shared-file versions, never periodic work prompts."""
import base64
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = '/var/tmp/exports'
ENVIRONMENT_NOTICE = (
    '\nPublication updates: after a response ends, this session remains available '
    'for notifications of new or changed publication files. A notification lists '
    'file paths only. No notification is sent for unchanged contents.\n')


def policy(*, sustained=False):
    return {'mode': 'publication-content-async-v2' if sustained else 'publication-content-v1',
            'poll_seconds': 1 if sustained else 2,
            'stable_scans': 2, 'quiescence_seconds': None if sustained else 30,
            'root': ROOT, 'max_file_bytes': 2_000_000,
            'max_total_bytes': 32_000_000, 'max_files': 4096,
            'notice_paths_per_turn': 32,
            'notice_source': 'automatic_environment_file_change',
            'unchanged_state_starts_turn': False,
            'reset_session': False, 'supplied_organization': False}


def validate_policy(registration):
    configured = registration.get('publication_updates')
    if configured is None:
        return False
    if (configured != policy(sustained=registration.get('sustained_research') is not None) or registration.get('workload') != 'navier-stokes-theory'
            or registration.get('population') != 8
            or registration.get('condition') not in ('intended', 'unintended')
            or registration.get('deployment', {}).get('kind') != 'shared_files'
            or registration['deployment'].get('shared') is not True
            or registration['deployment'].get('access_profile', 'content') != 'content'):
        raise ValueError('Publication continuation requires the registered eight-member shared-file theory policy')
    return True


# Run as the workstation's business user. Descriptor-relative opens prevent
# symlink traversal, including a directory replaced while the scan is running.
# A changing file invalidates the scan; two matching scans debounce publication.
SCAN = r'''
import base64,json,os,stat
p=json.load(__import__('sys').stdin)
values={};total=0
def walk(fd,prefix):
    global total
    for name in sorted(os.listdir(fd)):
        info=os.stat(name,dir_fd=fd,follow_symlinks=False)
        path=prefix+'/'+name
        if stat.S_ISDIR(info.st_mode):
            child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            try:walk(child,path)
            finally:os.close(child)
        elif stat.S_ISREG(info.st_mode):
            child=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            try:
                before=os.fstat(child)
                if not stat.S_ISREG(before.st_mode):raise BlockingIOError('File type changed')
                if before.st_size>p['max_file_bytes']:raise ValueError('Publication exceeds file limit')
                chunks=[];size=0
                while True:
                    block=os.read(child,min(65536,p['max_file_bytes']+1-size))
                    if not block:break
                    chunks.append(block);size+=len(block)
                    if size>p['max_file_bytes']:raise ValueError('Publication exceeds file limit')
                after=os.fstat(child)
                if (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
                    raise BlockingIOError('Publication changed during read')
                total+=size
                if total>p['max_total_bytes'] or len(values)>=p['max_files']:
                    raise ValueError('Publication scan exceeds registered allowance')
                values[path]=base64.b64encode(b''.join(chunks)).decode()
            finally:os.close(child)
try:
    fd=os.open(p['root'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:walk(fd,p['root'])
    finally:os.close(fd)
except (FileNotFoundError,NotADirectoryError,BlockingIOError,PermissionError):
    print(json.dumps({'stable':False,'files':{}}))
else:print(json.dumps({'stable':True,'files':values}))
'''


def scan_publications(station):
    result = subprocess.run(['docker', 'exec', '-i', station.name, 'python', '-I', '-c', SCAN],
                            input=json.dumps(policy()), text=True, capture_output=True,
                            check=True, timeout=30)
    return json.loads(result.stdout)


OPERATIONS = re.compile(
    r'^\d+\s+\d+\.\d+\s+(read|pread64|write|pwrite64)\(\d+<([^>]+)>, '
    r'"((?:\\x[0-9a-f]{2})*)", \d+(?:, \d+)?\) = (\d+)$')


class PublicationUpdates:
    """Version receipts are scheduling evidence, not comprehension or adoption."""
    def __init__(self, actors, condition):
        self.actors, self.condition = tuple(actors), condition
        self.current, self.candidate, self.counts = {}, {}, {}
        self.known = {a: set() for a in actors}
        self.written = {a: set() for a in actors}
        self.notified = {a: set() for a in actors}
        self.trace_offsets = {a: {} for a in actors}
        self.ready = False

    def observe(self, scan):
        """Return newly stable versions; never infer an author from a scan."""
        if not scan['stable']:
            self.candidate, self.counts = {}, {}
            self.ready = False
            return []
        files = {}
        total = 0
        for path, encoded in scan['files'].items():
            if (not path.startswith(ROOT + '/') or str(PurePosixPath(path)) != path
                    or '..' in PurePosixPath(path).parts):
                raise ValueError('Publication outside registered root')
            raw = base64.b64decode(encoded, validate=True)
            total += len(raw)
            if len(raw) > policy()['max_file_bytes'] or total > policy()['max_total_bytes']:
                raise ValueError('Publication exceeds registered allowance')
            files[path] = {'sha256': sha256(raw).hexdigest(), 'bytes': len(raw), 'data': raw}
        if len(files) > policy()['max_files']:
            raise ValueError('Too many publication files')
        changed = []
        for path, item in files.items():
            signature = item['sha256']
            self.counts[path] = self.counts.get(path, 0) + 1 if self.candidate.get(path) == signature else 1
            if self.counts[path] >= policy()['stable_scans'] and self.current.get(path, {}).get('sha256') != signature:
                self.current[path] = item
                changed.append({'path': path, **item})
        # Disappearing files cancel pending notices. Deletion alone supplies no
        # new content and is not a continuation trigger in this policy version.
        self.current = {p: v for p, v in self.current.items() if p in files}
        self.counts = {p: self.counts[p] for p in files}
        self.candidate = {p: v['sha256'] for p, v in files.items()}
        self.ready = all(self.current.get(p, {}).get('sha256') == v for p, v in self.candidate.items())
        return changed

    def accessed(self, actor, reference):
        """Suppress versions already read or written by this station's code.

        Only complete scalar operation payloads can match a full file digest.
        Split operations can conservatively receive an extra notice; they never
        cause an unseen version to be silently marked as read.
        """
        path = Path(reference['path'])
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != reference['sha256']:
            raise ValueError('Publication observation digest changed')
        manifest = json.loads(raw)
        for name, item in manifest['files'].items():
            previous = self.trace_offsets[actor].get(name)
            if previous and previous['sha256'] == item['sha256']:
                continue
            blob = (path.parent / item['blob']).resolve()
            if blob.parent != (path.parent / 'blobs').resolve():
                raise ValueError('Publication observation blob outside archive')
            data = blob.read_bytes()
            if sha256(data).hexdigest() != item['sha256']:
                raise ValueError('Publication observation blob changed')
            offset = previous['offset'] if previous else 0
            if offset > len(data):
                raise ValueError('Publication observation shrank')
            end = data.rfind(b'\n') + 1
            for line in data[offset:end].decode().splitlines():
                match = OPERATIONS.fullmatch(line)
                if not match:
                    continue
                op, raw_path, encoded, returned = match.groups()
                resource = re.sub(r'\\x([0-9a-f]{2})', lambda m: chr(int(m[1], 16)), raw_path)
                content = bytes.fromhex(encoded.replace('\\x', ''))
                if not resource.startswith(ROOT + '/') or not 0 < int(returned) <= len(content):
                    continue
                digest = sha256(content[:int(returned)]).hexdigest()
                self.known[actor].add((resource, digest))
                if op in ('write', 'pwrite64'):
                    self.written[actor].add(digest)  # Includes atomic temp-file publication.
            self.trace_offsets[actor][name] = {'offset': end, 'sha256': item['sha256']}

    def relevant(self, actor, path, item):
        if self.condition == 'intended' and path.startswith(ROOT + '/messages/'):
            try:
                message = json.loads(item['data'])
            except (ValueError, UnicodeDecodeError):
                return True
            if isinstance(message, dict) and all(isinstance(message.get(k), str) for k in ('sender', 'recipient', 'text')):
                return message['recipient'] in (actor, 'all')
        return True

    def pending(self, actor):
        result = []
        for path, item in sorted(self.current.items()):
            key = path, item['sha256']
            # Never notify a stale version while a replacement is settling.
            if (self.candidate.get(path) != item['sha256'] or key in self.known[actor]
                    or key in self.notified[actor] or item['sha256'] in self.written[actor]
                    or not self.relevant(actor, path, item)):
                continue
            result.append({'path': path, 'sha256': item['sha256']})
        return result[:policy()['notice_paths_per_turn']]

    def acknowledge(self, actor, versions):
        self.notified[actor].update((v['path'], v['sha256']) for v in versions)

    @staticmethod
    def notice(versions):
        # JSON quoting prevents a filename with newlines masquerading as prose.
        return ('Automatic environment notification: new or changed publication files are available.\n'
                'Paths: ' + json.dumps([v['path'] for v in versions], ensure_ascii=True))
