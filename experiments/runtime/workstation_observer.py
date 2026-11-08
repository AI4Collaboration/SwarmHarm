"""Quiescent snapshots for a continuously running private workstation."""

import base64
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time


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


def resume(processes):
    for item in processes:
        try:
            current = process_info(item['pid'])
            if current['start_ticks'] == item['start_ticks']:
                os.kill(item['pid'], signal.SIGCONT)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass


def freeze(observe_traced=False):
    stopped, observed = {}, {}
    subject_uid = 65534 if observe_traced else os.getuid()
    try:
        for _ in range(20):
            active = False
            for path in Path('/proc').iterdir():
                if not path.name.isdigit() or int(path.name) in (1, os.getpid()):
                    continue
                try:
                    item = process_info(path.name)
                    observer = observe_traced and item['uid'] == 0 and item['name'] == 'strace'
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
                        active = True
                        continue
                    stopped.setdefault(key, item)
                    os.kill(item['pid'], signal.SIGSTOP)
                    active = True
                except (FileNotFoundError, ProcessLookupError, PermissionError):
                    continue
            if not active:
                return list(stopped.values()), list(observed.values())
            time.sleep(.005)
        raise RuntimeError('Workstation processes did not settle for observation')
    except BaseException:
        resume(stopped.values())
        raise


def snapshot(extra_roots=(), observe_traced=False):
    if any(root != '/var/tmp/exports' for root in extra_roots):
        raise ValueError('Unknown additional observation root')
    stopped, processes = freeze(observe_traced)
    try:
        result = {'processes': processes, 'resume_processes': stopped,
                  'file_metadata': {}, 'temporary_files': {},
                  'captured_at_ns': time.time_ns()}
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
                                'mode': stat.S_IMODE(info.st_mode), 'inode': info.st_ino}
                    if kind == 'symlink':
                        metadata['target'] = os.readlink(path)
                    result['file_metadata'][str(path)] = metadata
                    if kind != 'file':
                        continue
                    limit = 32_000_000 if root in ('/tmp', '/private/tmp') else 2_000_000
                    if info.st_size > limit:
                        raise RuntimeError('Workstation file exceeds capture limit')
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
        print(json.dumps(snapshot([arg for arg in args if arg != '--observe-traced'], traced)))
