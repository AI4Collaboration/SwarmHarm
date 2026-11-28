"""Quiescent snapshots for a continuously running private workstation."""

import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import tempfile
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


def stop_traced_threads(item, tracer):
    """Stop each runnable thread while its managed ptrace controller is stopped."""
    pending = []
    for path in (Path('/proc') / str(item['pid']) / 'task').iterdir():
        try:
            status = dict(line.split(':', 1) for line in (path / 'status').read_text().splitlines())
        except (FileNotFoundError, ProcessLookupError):
            continue
        state = status['State'].strip()[0]
        controller = int(status['TracerPid'])
        if state in ('T', 'Z', 'X') or (state == 't' and controller == tracer['pid']):
            continue
        tid = int(path.name)
        pending.append((tid, state, controller))
    if pending:
        signal_process(item, signal.SIGSTOP)
    return pending


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


def freeze(observe_traced=False, subject_uid=None, settle_seconds=2, *, account_view=False, hard_deadline=None):
    if type(settle_seconds) is not int or settle_seconds not in (2, 10):
        raise ValueError('Unregistered observation settling allowance')
    stopped, observed = {}, {}
    subject_uid = (65534 if observe_traced else os.getuid()) if subject_uid is None else subject_uid
    if type(subject_uid) is not int or not 0<=subject_uid<2**32-1:raise ValueError('Invalid observed account')
    deadline = time.monotonic() + settle_seconds
    if hard_deadline is not None:
        deadline = min(deadline, hard_deadline)
    final_check = False
    nudged = {}
    mount_namespace = os.readlink('/proc/self/ns/mnt') if account_view else None
    try:
        while True:
            pending = []
            for path in Path('/proc').iterdir():
                if not path.name.isdigit() or int(path.name) in (1, os.getpid()):
                    continue
                try:
                    owner = path.stat().st_uid
                    if owner != subject_uid:
                        if not observe_traced or owner != 0:
                            continue
                        if (path / 'comm').read_text().strip() != 'strace':
                            continue
                        if account_view and os.readlink(path / 'ns/mnt') != mount_namespace:
                            continue
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
                    if observe_traced and item['tracer_pid'] and item['state'] not in ('D', 'Z', 'X'):
                        tracer = process_info(item['tracer_pid'])
                        if (tracer['uid'] == 0 and tracer['name'] == 'strace' and tracer['state'] == 'T'
                                and (not account_view or os.readlink(Path('/proc') / str(tracer['pid']) / 'ns/mnt') == mount_namespace)):
                            busy_threads = stop_traced_threads(item, tracer)
                            if busy_threads:
                                stopped.setdefault(key, item)
                                pending.extend(busy_threads)
                                since = nudged.setdefault(key, time.monotonic())
                                tracer_key = (tracer['pid'], tracer['start_ticks'])
                                if time.monotonic() - since >= .03 and tracer_key in stopped:
                                    # The controller must service pending ptrace events before
                                    # a tracee in exec or group-stop can acknowledge SIGSTOP.
                                    resume([stopped.pop(tracer_key)])
                                    time.sleep(.05)
                                    nudged.pop(key, None)
                                    break
                            else:
                                nudged.pop(key, None)
                            continue
                    if item['state'] in ('T', 'Z', 'X'):
                        continue
                    if observe_traced and item['state'] == 'D' and item['tracer_pid']:
                        try:
                            tracer = process_info(item['tracer_pid'])
                            managed = tracer['uid'] == 0 and tracer['name'] == 'strace'
                            if managed and account_view:
                                managed = os.readlink(Path('/proc') / str(tracer['pid']) / 'ns/mnt') == mount_namespace
                        except (FileNotFoundError, ProcessLookupError):
                            managed = False
                        if managed:
                            # A vfork parent may need both its child and tracer
                            # to run before it can process a stop.
                            resume(stopped.values())
                            stopped.clear()
                            pending.append((item['pid'], 'D', tracer['pid']))
                            while time.monotonic() < deadline:
                                time.sleep(.005)
                                try:
                                    current = process_info(item['pid'])
                                except (FileNotFoundError, ProcessLookupError):
                                    break
                                if (current['start_ticks'], current['state'], current['tracer_pid']) != (item['start_ticks'], 'D', tracer['pid']):
                                    break
                            break
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
            if final_check:
                raise ObservationNotSettled(f'Workstation processes did not settle for observation: {pending}')
            # Confirm delivered stop signals even if the scan itself consumed
            # the settling interval on a heavily populated shared workstation.
            final_check = time.monotonic() >= deadline
            time.sleep(.005)
    except BaseException:
        resume(stopped.values())
        raise


BLOB_DIR = Path('/var/log/workstation/.artifacts')
INLINE_BYTES = 2 * 1024 * 1024


def file_value(stream, opened, archive_large):
    if not archive_large or opened.st_size <= INLINE_BYTES:
        data = stream.read()
        return base64.b64encode(data).decode(), len(data)
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    BLOB_DIR.mkdir(mode=0o700, exist_ok=True)
    cached = BLOB_DIR / digest
    if cached.is_file():
        return {'blob': digest, 'bytes': cached.stat().st_size}, cached.stat().st_size
    stream.seek(0)
    with tempfile.NamedTemporaryFile(dir=BLOB_DIR, delete=False) as out:
        tmp = Path(out.name)
        fingerprint = hashlib.sha256()
        try:
            while block := stream.read(1024 * 1024):
                out.write(block)
                fingerprint.update(block)
            size = out.tell()
            out.flush()
            digest = fingerprint.hexdigest()
            tmp.replace(BLOB_DIR / digest)
        finally:
            tmp.unlink(missing_ok=True)
    return {'blob': digest, 'bytes': size}, size


def snapshot(extra_roots=(), observe_traced=False, subject_uid=None, settle_seconds=2, *, account_view=False, archive_large=False):
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
            if observe_traced and settle_seconds == 10 and len(retries) == 2:
                # The last attempt uses the remaining registered allowance after
                # earlier attempts released all subjects and the tracer.
                stopped, processes = freeze(observe_traced, subject_uid, settle_seconds,
                                            account_view=account_view,
                                            hard_deadline=before_freeze + settle_seconds)
            else:
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
            values = {}
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
                    try:
                        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                        with os.fdopen(fd, 'rb') as stream:
                            opened = os.fstat(stream.fileno())
                            if not stat.S_ISREG(opened.st_mode):
                                raise ValueError('Capture target changed type')
                            value, size = file_value(stream, opened, archive_large and root != '/registry')
                            after = os.fstat(stream.fileno())
                        if root in extra_roots:
                            metadata.update(bytes=size, mtime_ns=opened.st_mtime_ns,
                                            inode=opened.st_ino, mode=stat.S_IMODE(opened.st_mode),
                                            stable_during_read=(size == opened.st_size == after.st_size
                                                and opened.st_mtime_ns == after.st_mtime_ns
                                                and opened.st_ctime_ns == after.st_ctime_ns))
                        if isinstance(value, dict):
                            metadata['sha256'] = value['blob']
                        values[str(path)] = value
                    except (OSError, ValueError) as error:
                        if root not in extra_roots:
                            raise
                        result['capture_gaps'].append({'path': str(path), 'reason': str(error)})
            if root in ('/tmp', '/private/tmp'):
                result['temporary_files'].update(values)
            else:
                result[root] = values
        return result
    except BaseException:
        resume(stopped)
        raise


def emit_snapshot(values, *, resume_inline=False):
    """Only fully inlined observations may release their own frozen processes here."""
    areas = ('/workspace', '/registry', '/var/tmp/exports', 'temporary_files')
    try:
        eligible = resume_inline and all(
            isinstance(value, str)
            for area in areas for value in values.get(area, {}).values())
        if eligible:
            values['inline_resume_completed'] = True
        # Finish serialization before release: no mutable guest files are needed afterward.
        output = json.dumps(values)
        if eligible:
            resume(values['resume_processes'])
        print(output)
    except BaseException:
        resume(values['resume_processes'])
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
        values = snapshot([arg for arg in args if arg not in ('--observe-traced', '--account-view', '--archive-large', '--resume-inline') and not arg.startswith(('--subject-uid=','--settle-seconds='))], traced, uids[0] if uids else None, allowances[0] if allowances else 2, account_view='--account-view' in args, archive_large='--archive-large' in args)
        emit_snapshot(values, resume_inline='--resume-inline' in args and '--account-view' not in args)
