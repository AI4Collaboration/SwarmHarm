"""Actor-scoped, mediated views of disposable native session files.

No operator directory is mounted in a subject workstation. Before a shell tool,
native bytes are copied into that actor's temporary home. Only edits to those
same files can be applied back, with external before/after evidence retained.
This is an explicit experimental adapter, not a stock harness vulnerability claim.
"""
from contextlib import nullcontext
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import threading

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


def apply_view(directory, before, after, *, writable, preserve_inode=False):
    """Apply only captured filenames; all addresses originate with the recorder."""
    directory = Path(directory)
    if any(Path(name).name != name or not name.endswith('.jsonl') for name in before):
        raise ValueError('Invalid native record filename')
    unknown = sorted(set(after) - set(before))
    changes = [name for name in before if after.get(name) != before[name]]
    if writable:
        for name in changes:
            target = directory / name
            data = after.get(name, b'')
            if name not in after and not preserve_inode:
                target.unlink(missing_ok=True)
                continue
            if len(data) > LIMIT:
                raise ValueError('Modified record exceeds registered capture limit')
            if preserve_inode:
                # Caller quiesces the registered native writer. Keep its open
                # append descriptor attached to the same file, including deletion.
                fd = os.open(target, os.O_WRONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'wb') as handle:
                    handle.write(data)
                    handle.truncate()
                    handle.flush()
                continue
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


def merge_native_append(before, after, current):
    """Rebase captured-file edits over native append-only activity, never rewrites."""
    if set(current) != set(before) or any(
            not current[name].startswith(data) for name, data in before.items()):
        raise ValueError('Native record changed beyond append-only activity')
    merged = {name: data for name, data in after.items() if name not in before}
    for name, data in before.items():
        suffix = current[name][len(data):]
        if name in after:
            merged[name] = after[name] + suffix
        elif suffix:
            merged[name] = suffix
    return merged


class NativeRecordSurface:
    def __init__(self, root, actors, *, writable=True, apply_mode='immediate', harness='pi-sdk'):
        if apply_mode not in ('immediate', 'staged'):
            raise ValueError('Unknown native-record application mode')
        self.root = Path(root).resolve()
        self.actors = set(actors)
        self.harness = harness
        self.view = VIEW if harness=='pi-sdk' else '/tmp/agent/activity'
        self.bound_directories = {}
        self.writer_guards = {}
        self.writable = writable
        self.apply_mode = apply_mode
        self.archive = self.root / 'operator' / 'record-observer'
        self.archive.mkdir(parents=True, exist_ok=True)
        self.counter = {actor: 0 for actor in actors}
        self.staged = {}
        self.lock = threading.Lock()

    def directory(self, actor):
        if actor not in self.actors or Path(actor).name != actor:
            raise ValueError('Unknown record owner')
        if actor in self.bound_directories:
            return self.bound_directories[actor]
        if self.harness=='pi-sdk':
            return self.root / actor / 'pi' / 'session'
        return self.root / actor / ('claude' if self.harness=='claude-code' else 'codex')

    def bind(self, actor, session_file, *, writer_guard=None):
        if actor not in self.actors or self.harness != 'codex':
            raise ValueError('Unexpected native session binding')
        path=Path(session_file).resolve()
        if path.suffix != '.jsonl' or (path.exists() and not path.is_file()):
            raise ValueError('Native session file is unavailable')
        if writer_guard is None:
            raise ValueError('Live native session requires a writer guard')
        self.bound_directories[actor]=path.parent
        self.writer_guards[actor]=writer_guard

    def writer_guard(self, actor):
        return self.writer_guards.get(actor, nullcontext)()

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

    def staged_revision(self, actor):
        if actor not in self.actors:
            raise ValueError('Unknown record owner')
        with self.lock:
            row = self.staged.get(actor)
            if row is None:
                return None
            return {
                'owner': actor,
                'revision_sha256': row['revision_sha256'],
                'changed_files': list(row['changed_files']),
                'before': self.retain(actor, row['base']),
                'after': self.retain(actor, row['after']),
            }

    def apply_staged(self, revisions):
        """Apply one exact multi-owner set after the business layer confirms it."""
        if self.apply_mode != 'staged' or not self.writable:
            raise ValueError('Staged record application is not available')
        if len(revisions) < 2:
            raise ValueError('A record revision set requires multiple owners')
        with self.lock:
            selected = {}
            for actor, expected in revisions.items():
                row = self.staged.get(actor)
                if row is None or row['revision_sha256'] != expected:
                    raise ValueError('Staged record revision changed')
                current = read_regular(self.directory(actor))
                # The harness keeps recording the subject's later tool interactions after
                # the subject stages a revision. Preserve only byte-exact append
                # suffixes; any replacement, truncation, deletion, or new file is
                # still an unregistered concurrent change and rejects the set.
                if set(current) != set(row['base']):
                    raise ValueError('Native record set changed after the revision was staged')
                effective_after = {}
                for name, base in row['base'].items():
                    latest = current[name]
                    if not latest.startswith(base):
                        raise ValueError('Native record changed non-append-only after the revision was staged')
                    suffix = latest[len(base):]
                    if name in row['after']:
                        effective_after[name] = row['after'][name] + suffix
                    elif suffix:
                        effective_after[name] = suffix
                selected[actor] = (current, row, effective_after)
            observations = []
            for actor, (before, row, effective_after) in selected.items():
                before_manifest = self.retain(actor, before)
                staged_subject_after = self.retain(actor, row['after'])
                subject_after = self.retain(actor, effective_after)
                mutation = apply_view(
                    self.directory(actor), before, effective_after, writable=True)
                self.counter[actor] += 1
                observation = {
                    'owner': actor,
                    'sequence': self.counter[actor],
                    'before': before_manifest,
                    'staged_subject_after': staged_subject_after,
                    'subject_after': subject_after,
                    'native_pre_apply': before_manifest,
                    'native_after': self.capture(actor),
                    'mutation': mutation,
                    'staged_revision_sha256': row['revision_sha256'],
                    'appended_native_bytes_preserved': sum(
                        len(before[name]) - len(row['base'][name]) for name in before),
                }
                path = self.archive / f'{actor}-{self.counter[actor]:04d}.json'
                with path.open('x') as handle:
                    json.dump(observation, handle, indent=2)
                observations.append(observation)
            for actor in selected:
                del self.staged[actor]
            return observations

    def station(self, actor, files):
        surface = self
        class Station(DockerWorkstation):
            def __init__(self):
                super().__init__(files, environment={'HOME': '/tmp/agent'})

            def execute(self, command, shared):
                with surface.writer_guard(actor):
                    native_before = read_regular(surface.directory(actor))
                with surface.lock:
                    pending = surface.staged.get(actor)
                    append_only = (pending is not None
                        and set(pending['base']) == set(native_before)
                        and all(native_before[name].startswith(base)
                                for name, base in pending['base'].items()))
                    if append_only:
                        view_before = {}
                        for name, base in pending['base'].items():
                            suffix = native_before[name][len(base):]
                            if name in pending['after']:
                                view_before[name] = pending['after'][name] + suffix
                            elif suffix:
                                view_before[name] = suffix
                    else:
                        if pending is not None:
                            del surface.staged[actor]
                        view_before = native_before
                before_manifest = surface.retain(actor, native_before)
                self.resume()
                # Clear only this disposable view before hydrating the current bytes.
                code = "import shutil,pathlib; p=pathlib.Path('/tmp/agent/.pi/sessions'); shutil.rmtree(p,ignore_errors=True); p.mkdir(parents=True,exist_ok=True)"
                subprocess.run(['docker','exec',self.name,'python','-I','-c',code.replace(VIEW,surface.view)],
                               check=True, capture_output=True, timeout=15)
                self.hydrate({surface.view+'/'+name:base64.b64encode(data).decode()
                              for name,data in view_before.items()}, False)
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
                    ['docker','exec',self.name,'python','-I','-c',code.replace(VIEW,surface.view)], timeout=15))
                self.pause()
                after = {name:base64.b64decode(value) for name,value in raw['files'].items()}
                observed = surface.retain(actor, after)
                with surface.writer_guard(actor):
                    current=read_regular(surface.directory(actor))
                    pre_apply=surface.retain(actor,current)
                    if raw['invalid'] or raw['invalid_directory']:
                        mutation = {'applied':False,'rejected':'non_regular_record_view'}
                    elif current != native_before and (surface.apply_mode != 'immediate'
                            or set(current) != set(native_before)
                            or any(not current[name].startswith(data)
                                   for name,data in native_before.items())):
                        mutation = {'applied':False,'rejected':'native_record_changed_during_command'}
                    elif surface.apply_mode == 'staged':
                        # A pending revision is hydrated together with any later
                        # append-only native activity. A command that leaves that view
                        # unchanged has not authored a new revision: keep the
                        # original base, subject bytes and revision identity. This
                        # prevents ordinary reads or later tool calls from
                        # invalidating an already filed transaction member.
                        comparison_before = view_before if append_only else native_before
                        changes = [name for name in native_before
                                   if after.get(name) != comparison_before.get(name)]
                        unknown = sorted(set(after) - set(native_before))
                        if changes and surface.writable:
                            revision_sha256 = sha256(json.dumps({
                                'owner': actor,
                                'base': {name: sha256(data).hexdigest()
                                         for name, data in sorted(native_before.items())},
                                'after': {name: sha256(data).hexdigest()
                                          for name, data in sorted(after.items())
                                          if name in native_before},
                            }, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                            with surface.lock:
                                surface.staged[actor] = {
                                    'base': native_before,
                                    'after': {name: after[name] for name in native_before if name in after},
                                    'changed_files': sorted(changes),
                                    'revision_sha256': revision_sha256,
                                }
                            mutation = {
                                'applied': False,
                                'staged': True,
                                'changed_files': sorted(changes),
                                'unknown_files_not_staged': unknown,
                                'revision_sha256': revision_sha256,
                                'condition': 'staged',
                            }
                        elif append_only and pending is not None:
                            mutation = {
                                'applied': False,
                                'staged': True,
                                'staged_revision_preserved': True,
                                'changed_files': [],
                                'unknown_files_not_staged': unknown,
                                'revision_sha256': pending['revision_sha256'],
                                'condition': 'staged',
                            }
                        else:
                            mutation = {
                                'applied': False,
                                'staged': False,
                                'changed_files': sorted(changes),
                                'unknown_files_not_staged': unknown,
                                'condition': 'staged',
                            }
                    else:
                        effective = merge_native_append(native_before, after, current)
                        mutation = apply_view(surface.directory(actor), current, effective,
                                              writable=surface.writable,
                                              preserve_inode=actor in surface.writer_guards)
                        mutation['live_writer_inode_preserved'] = actor in surface.writer_guards
                        mutation['concurrent_append_bytes_preserved'] = sum(
                            len(current[name])-len(data) for name,data in native_before.items())
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
