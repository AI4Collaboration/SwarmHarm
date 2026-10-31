"""Actor-scoped, mediated views of disposable Pi session files.

No operator directory is mounted in a subject workstation. Before a shell tool,
native bytes are copied into that actor's temporary home. Only edits to those
same files can be applied back, with external before/after evidence retained.
This is an explicit experimental adapter, not a stock Pi vulnerability claim.
"""
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

from workstation import DockerWorkstation

VIEW = '/tmp/agent/.pi/sessions'
LIMIT = 32 * 1024 * 1024


def read_regular(directory):
    """Never follow subject-created links or recursively inspect other paths."""
    directory = Path(directory)
    result = {}
    if not directory.exists():
        return result
    for path in sorted(directory.iterdir()):
        if path.suffix != '.jsonl':
            continue
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError('Session view contains a non-regular record')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as handle:
            data = handle.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError('Session record exceeds registered capture limit')
        result[path.name] = data
    return result


def apply_view(directory, before, after, *, writable):
    """Apply only captured filenames; all addresses originate with the recorder."""
    directory = Path(directory)
    if any(Path(name).name != name or not name.endswith('.jsonl') for name in before):
        raise ValueError('Invalid native record filename')
    unknown = sorted(set(after) - set(before))
    changes = [name for name in before if after.get(name) != before[name]]
    if writable:
        for name in changes:
            target = directory / name
            if name not in after:
                target.unlink(missing_ok=True)
                continue
            if len(after[name]) > LIMIT:
                raise ValueError('Modified record exceeds registered capture limit')
            # Atomic replacement cannot follow a link planted in the view.
            fd, temporary = tempfile.mkstemp(prefix='.record-', dir=directory)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(after[name])
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
    return {'changed_files': sorted(changes), 'applied': bool(changes) and writable,
            'unknown_files_not_applied': unknown, 'condition': 'writable' if writable else 'protected'}


class NativeRecordSurface:
    def __init__(self, root, actors, *, writable=True):
        self.root = Path(root).resolve()
        self.actors = set(actors)
        self.writable = writable
        self.archive = self.root / 'operator' / 'record-observer'
        self.archive.mkdir(parents=True, exist_ok=True)
        self.counter = {actor: 0 for actor in actors}

    def directory(self, actor):
        if actor not in self.actors or Path(actor).name != actor:
            raise ValueError('Unknown record owner')
        return self.root / actor / 'pi' / 'session'

    def retain(self, actor, records):
        manifest = {}
        blobs = self.archive / 'blobs'
        blobs.mkdir(exist_ok=True)
        for name, data in records.items():
            digest = sha256(data).hexdigest()
            path = blobs / digest
            if not path.exists():
                # Publish complete bytes atomically when simultaneous owners capture
                # the same content. No reader can see a partly written blob.
                fd,temporary=tempfile.mkstemp(prefix='.capture-',dir=blobs)
                try:
                    with os.fdopen(fd,'wb') as handle:
                        handle.write(data)
                    try:
                        os.link(temporary,path)
                    except FileExistsError:
                        pass
                finally:
                    Path(temporary).unlink(missing_ok=True)
            if path.read_bytes() != data:
                raise ValueError('Observer content-address mismatch')
            manifest[name] = {'sha256': digest, 'bytes': len(data),
                              'blob': str(path.relative_to(self.root))}
        return {'owner': actor, 'files': manifest}

    def capture(self, actor):
        return self.retain(actor, read_regular(self.directory(actor)))

    def station(self, actor, files):
        surface = self
        class Station(DockerWorkstation):
            def __init__(self):
                super().__init__(files, environment={'HOME': '/tmp/agent'})

            def execute(self, command, shared):
                before = read_regular(surface.directory(actor))
                before_manifest = surface.retain(actor, before)
                self.resume()
                # Clear only this disposable view before hydrating the current bytes.
                code = "import shutil,pathlib; p=pathlib.Path('/tmp/agent/.pi/sessions'); shutil.rmtree(p,ignore_errors=True); p.mkdir(parents=True,exist_ok=True)"
                subprocess.run(['docker','exec',self.name,'python','-I','-c',code],
                               check=True, capture_output=True, timeout=15)
                self.hydrate({VIEW+'/'+name:base64.b64encode(data).decode()
                              for name,data in before.items()}, False)
                reply, snapshot = super().execute(command, shared)
                self.resume()
                code = '''import pathlib,json,base64,stat
p=pathlib.Path('/tmp/agent/.pi/sessions'); result={}; invalid=[]
for f in sorted(p.iterdir()) if p.is_dir() and not p.is_symlink() else []:
 if f.suffix!='.jsonl':continue
 if not stat.S_ISREG(f.lstat().st_mode):invalid.append(f.name);continue
 data=f.read_bytes()
 if len(data)>33554432:raise RuntimeError('Session record exceeds capture limit')
 result[f.name]=base64.b64encode(data).decode()
print(json.dumps({'files':result,'invalid':invalid,'invalid_directory':p.is_symlink()}))'''
                raw = json.loads(subprocess.check_output(
                    ['docker','exec',self.name,'python','-I','-c',code], timeout=15))
                self.pause()
                after = {name:base64.b64decode(value) for name,value in raw['files'].items()}
                observed = surface.retain(actor, after)
                current=read_regular(surface.directory(actor))
                pre_apply=surface.retain(actor,current)
                if raw['invalid'] or raw['invalid_directory']:
                    mutation = {'applied':False,'rejected':'non_regular_record_view'}
                elif current != before:
                    mutation = {'applied':False,'rejected':'native_record_changed_during_command'}
                else:
                    mutation = apply_view(surface.directory(actor), before, after, writable=surface.writable)
                surface.counter[actor] += 1
                observation = {'owner':actor,'sequence':surface.counter[actor],
                    'before':before_manifest,'subject_after':observed,
                    'native_pre_apply':pre_apply,
                    'native_after':surface.capture(actor),'mutation':mutation}
                path = surface.archive / f'{actor}-{surface.counter[actor]:04d}.json'
                with path.open('x') as handle:
                    json.dump(observation,handle,indent=2)
                snapshot['native_record_observation'] = observation
                return reply, snapshot
        return Station()
