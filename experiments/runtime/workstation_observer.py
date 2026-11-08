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
    return {'pid': int(pid), 'state': fields[0], 'parent': int(fields[1]),
            'start_ticks': fields[19], 'uid': path.stat().st_uid,
            'command': (path / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')}


def resume(processes):
    for item in processes:
        try:
            current = process_info(item['pid'])
            if current['start_ticks'] == item['start_ticks']:
                os.kill(item['pid'], signal.SIGCONT)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass


def freeze():
    stopped, observed = {}, {}
    try:
        for _ in range(20):
            active = False
            for path in Path('/proc').iterdir():
                if not path.name.isdigit() or int(path.name) in (1, os.getpid()):
                    continue
                try:
                    item = process_info(path.name)
                    if item['uid'] != os.getuid():
                        continue
                    key = (item['pid'], item['start_ticks'])
                    observed.setdefault(key, item)
                    if item['state'] in ('T', 't', 'Z', 'X'):
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


def snapshot():
    stopped, processes = freeze()
    try:
        result = {'processes': processes, 'resume_processes': stopped,
                  'file_metadata': {}, 'temporary_files': {},
                  'captured_at_ns': time.time_ns()}
        for root in ('/workspace', '/registry', '/tmp', '/private/tmp'):
            values, total = {}, 0
            for folder, dirs, names in os.walk(root, followlinks=False):
                for name in sorted(set(dirs + names)):
                    path = Path(folder) / name
                    info = path.lstat()
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
        print(json.dumps(snapshot()))
