"""Quiescent snapshots for a continuously running private workstation."""

import base64
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time


class ObservationNotSettled(RuntimeError):
    """No snapshot was taken; every process stopped by this attempt was resumed."""


def process_info(pid):
    path = Path('/proc') / str(pid)
    raw = (path / 'stat').read_text()
    fields = raw.rsplit(') ', 1)[1].split()
    status = dict(line.split(':', 1) for line in (path / 'status').read_text().splitlines())
    return {'pid': int(pid), 'state': fields[0], 'parent': int(fields[1]),
            'start_ticks': fields[19], 'uid': path.stat().st_uid,
            'tracer_pid': int(status.get('TracerPid', '0')),
            'name': (path / 'comm').read_text().strip(),
            'command': (path / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')}


def signal_process(process, sig):
    """Signal the observed process with its own UID when the observer lacks CAP_KILL."""
    try:
        os.kill(process['pid'], sig)
    except PermissionError:
        caller = os.geteuid()
        if caller != 0 or process['uid'] == caller:
            raise
        os.seteuid(process['uid'])
        try:
            os.kill(process['pid'], sig)
        finally:
            os.seteuid(caller)


def resume(processes):
    denied = []
    for item in processes:
        try:
            current = process_info(item['pid'])
            if current['start_ticks'] == item['start_ticks']:
                signal_process(current, signal.SIGCONT)
        except (FileNotFoundError, ProcessLookupError):
            pass
        except PermissionError:
            denied.append(item['pid'])
    if denied:
        raise PermissionError(f'Workstation processes could not be resumed: {denied}')


def freeze(observe_traced=False, subject_uid=None, settle_seconds=2, *, account_view=False):
    if type(settle_seconds) is not int or settle_seconds not in (2, 10):
        raise ValueError('Unregistered observation settling allowance')
    stopped, observed = {}, {}
    subject_uid = (65534 if observe_traced else os.getuid()) if subject_uid is None else subject_uid
    if type(subject_uid) is not int or not 0<=subject_uid<2**32-1:raise ValueError('Invalid observed account')
    deadline = time.monotonic() + settle_seconds
    try:
        while True:
            pending = []
            for path in Path('/proc').iterdir():
                if not path.name.isdigit() or int(path.name) in (1, os.getpid()):
                    continue
                try:
                    item = process_info(path.name)
                except (FileNotFoundError, ProcessLookupError, PermissionError):
                    continue
                try:
                    observer = observe_traced and item['uid'] == 0 and item['name'] == 'strace'
                    if observer and account_view:
                        observer = os.readlink(path/'ns/mnt') == os.readlink('/proc/self/ns/mnt')
                    if item['uid'] != subject_uid and not observer:
                        continue
                    key = (item['pid'], item['start_ticks'])
                    observed.setdefault(key, item)
                    if item['state'] in ('T', 'Z', 'X'):
                        continue
                    if item['state'] == 't':
                        if not observe_traced:
                            continue
                        # A ptrace stop is transient while its tracer is running.
                        # It is quiescent only after that tracer has also stopped.
                        tracer = process_info(item['tracer_pid'])
                        if tracer['state'] in ('T', 'Z', 'X'):
                            continue
                        pending.append((item['pid'], 't', item['tracer_pid']))
                        continue
                    signal_process(item, signal.SIGSTOP)
                    stopped.setdefault(key, item)
                    pending.append((item['pid'], item['state'], item['tracer_pid']))
                except (FileNotFoundError, ProcessLookupError):
                    continue
            if not pending:
                return list(stopped.values()), list(observed.values())
            if time.monotonic() >= deadline:
                raise ObservationNotSettled(f'Workstation processes did not settle for observation: {pending}')
            time.sleep(.005)
    except BaseException:
        resume(stopped.values())
        raise


def snapshot(extra_roots=(), observe_traced=False, subject_uid=None, settle_seconds=2, *, account_view=False):
    if any(root != '/var/tmp/exports' for root in extra_roots):
        raise ValueError('Unknown additional observation root')
    before_freeze = time.monotonic()
    if type(settle_seconds) is not int or settle_seconds not in (2, 10):
        raise ValueError('Unregistered observation settling allowance')
    retries=[]
    while True:
        try:
            # A traced process can remain blocked while another process is stopped.
            # Release an unsuccessful freeze before retrying; never call D/S/R quiescent.
            stopped, processes = (freeze(observe_traced,subject_uid, account_view=True) if account_view
                                  else freeze(observe_traced,subject_uid))
            break
        except ObservationNotSettled as error:
            if settle_seconds==2 or len(retries)>=2 or time.monotonic()-before_freeze>settle_seconds-2.05:
                raise
            retries.append({'at_ns':time.time_ns(),'failure':str(error),'all_stopped_processes_resumed':True})
            time.sleep(.05)
    settling_elapsed = time.monotonic() - before_freeze
    try:
        result = {'processes': processes, 'resume_processes': stopped,
                  'file_metadata': {}, 'temporary_files': {},
                  'captured_at_ns': time.time_ns()}
        if settle_seconds != 2:
            result['quiescence'] = {'settle_allowance_seconds': settle_seconds,
                                    'actual_wait_seconds': settling_elapsed,
                                    'released_attempts':retries,
                                    'all_observed_processes_settled': True}
        if extra_roots:
            result['concurrent_roots'] = list(extra_roots)
            result['capture_gaps'] = []
        for root in ('/workspace', '/registry', '/tmp', '/private/tmp', *extra_roots):
            values, total = {}, 0
            for folder, dirs, names in os.walk(root, followlinks=False):
                for name in sorted(set(dirs + names)):
                    path = Path(folder) / name
                    try:
                        info = path.lstat()
                    except FileNotFoundError:
                        if root not in extra_roots:
                            raise
                        result['capture_gaps'].append({'path': str(path), 'reason': 'removed_before_stat'})
                        continue
                    kind = {stat.S_IFREG: 'file', stat.S_IFDIR: 'directory',
                            stat.S_IFLNK: 'symlink', stat.S_IFSOCK: 'socket',
                            stat.S_IFIFO: 'fifo'}.get(stat.S_IFMT(info.st_mode), 'special')
                    metadata = {'kind': kind, 'bytes': info.st_size,
                                'mtime_ns': info.st_mtime_ns,
                                'mode': stat.S_IMODE(info.st_mode), 'inode': info.st_ino, 'uid':info.st_uid, 'gid':info.st_gid}
                    if kind == 'symlink':
                        metadata['target'] = os.readlink(path)
                    result['file_metadata'][str(path)] = metadata
                    if kind != 'file':
                        continue
                    # Published research artifacts need the same capture capacity
                    # as private work products. The registry retains its smaller
                    # synchronization limit; root totals remain bounded below.
                    limit = 2_000_000 if root == '/registry' else 32_000_000
                    if info.st_size > limit:
                        raise RuntimeError(f'Workstation file exceeds capture limit: {path} ({info.st_size} > {limit})')
                    if root in extra_roots:
                        # Other stations remain live. Bind bytes and metadata to
                        # one open file, and report instability instead of calling
                        # the entire shared tree a single point-in-time snapshot.
                        try:
                            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                            with os.fdopen(fd, 'rb') as stream:
                                opened = os.fstat(stream.fileno())
                                if not stat.S_ISREG(opened.st_mode) or opened.st_size > limit:
                                    raise ValueError('Shared capture target changed type or size')
                                data = stream.read(limit + 1)
                                after = os.fstat(stream.fileno())
                            if len(data) > limit:
                                raise ValueError('Shared capture grew beyond its limit')
                            metadata.update(bytes=opened.st_size, mtime_ns=opened.st_mtime_ns,
                                            inode=opened.st_ino, mode=stat.S_IMODE(opened.st_mode),
                                            stable_during_read=(opened.st_size == after.st_size
                                                and opened.st_mtime_ns == after.st_mtime_ns
                                                and opened.st_ctime_ns == after.st_ctime_ns))
                        except (OSError, ValueError) as error:
                            result['capture_gaps'].append({'path': str(path), 'reason': str(error)})
                            continue
                    else:
                        data = path.read_bytes()
                    total += len(data)
                    if total > 64_000_000:
                        raise RuntimeError('Workstation root exceeds capture limit')
                    values[str(path)] = base64.b64encode(data).decode()
            if root in ('/tmp', '/private/tmp'):
                result['temporary_files'].update(values)
            else:
                result[root] = values
        return result
    except BaseException:
        resume(stopped)
        raise


if __name__ == '__main__':
    if sys.argv[1] == 'resume':
        resume(json.load(sys.stdin))
    else:
        args = sys.argv[2:]
        traced = '--observe-traced' in args
        uids=[int(arg.split('=',1)[1]) for arg in args if arg.startswith('--subject-uid=')]
        allowances=[int(arg.split('=',1)[1]) for arg in args if arg.startswith('--settle-seconds=')]
        if len(uids)>1:raise ValueError('Duplicate observed account')
        if len(allowances)>1:raise ValueError('Duplicate settling allowance')
        print(json.dumps(snapshot([arg for arg in args if arg not in ('--observe-traced', '--account-view') and not arg.startswith(('--subject-uid=','--settle-seconds='))], traced, uids[0] if uids else None, allowances[0] if allowances else 2, account_view='--account-view' in args)))
