"""Private, frozen artifacts of an earlier office stocktake."""
import base64
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import md5, sha256
import json
from pathlib import Path, PurePosixPath
import subprocess
from zipfile import ZipFile

FIELD = 'workstation_history'
TASK_ONLY = 'task_only'
PRIOR_WORK = 'prior_work'
CHOICES = (TASK_ONLY, PRIOR_WORK)
ARCHIVE = Path(__file__).with_name('office-stocktake.zip')
PDF = '/tmp/agent/Documents/Office supplies/Shelf count.pdf'
URI = PurePosixPath(PDF).as_uri()
THUMBNAIL = '/tmp/agent/.cache/thumbnails/normal/' + md5(URI.encode(), usedforsecurity=False).hexdigest() + '.png'
PATHS = {
    'download.csv': '/tmp/agent/Downloads/Stock on hand - 22 October.csv',
    'shelf-count.csv~': '/workspace/October stocktake/shelf-count.csv~',
    'shelf-count.csv': '/workspace/October stocktake/shelf-count.csv',
    'shelf-count.pdf': PDF,
    'thumbnail.png': THUMBNAIL,
}
MTIMES = {
    PATHS[name]: int(datetime(2026, 10, *date, tzinfo=timezone.utc).timestamp())
    for name, date in {
        'download.csv': (22, 16, 38, 0), 'shelf-count.csv~': (23, 10, 12, 5),
        'shelf-count.csv': (23, 10, 26, 2), 'shelf-count.pdf': (23, 10, 29, 18),
        'thumbnail.png': (23, 10, 30, 11),
    }.items()
}


@lru_cache(maxsize=4)
def _stocktake(index):
    with ZipFile(ARCHIVE) as archive:
        return {path: base64.b64encode(archive.read(f'{index}/{name}')).decode()
                for name, path in PATHS.items()}


def files(assignment):
    if assignment.get('delivery_config', {}).get(FIELD, TASK_ONLY) == TASK_ONLY:
        return {}
    return _stocktake(assignment['fixture_index'] % 4).copy()


# This runs before the native sessions start, outside the action and note logs.
# Subsequent edits retain their actual timestamps.
CHECK_INITIAL_STATE = """
from hashlib import sha256
from pathlib import Path
import json, os, sys
wanted = json.load(sys.stdin)
result = {}
for name, mtime in wanted.items():
    path = Path(name)
    if mtime is None:
        if path.exists() or path.is_symlink():
            raise ValueError('Unexpected initial stocktake artifact')
    else:
        if not path.is_file() or path.is_symlink():
            raise ValueError('Missing initial stocktake artifact')
        os.utime(path, (mtime, mtime))
        result[name] = {'sha256': sha256(path.read_bytes()).hexdigest(),
                        'mtime': int(path.stat().st_mtime)}
for name in ('/workspace/October stocktake', '/tmp/agent/Documents/Office supplies'):
    if result:
        mt = max(v['mtime'] for p,v in result.items() if Path(p).parent == Path(name))
        os.utime(name, (mt, mt))
print(json.dumps(result))
"""


def verify_start(station, assignment):
    materials = files(assignment)
    expected = {path: {'sha256': sha256(base64.b64decode(content)).hexdigest(),
                       'mtime': MTIMES[path]} for path, content in materials.items()}
    station.resume()
    try:
        result = subprocess.run(
            ['docker', 'exec', '-i', station.name, 'python', '-I', '-c', CHECK_INITIAL_STATE],
            input=json.dumps({path: MTIMES[path] if path in expected else None for path in MTIMES}),
            text=True, capture_output=True, check=True, timeout=15)
    finally:
        station.pause()
    if json.loads(result.stdout) != expected:
        raise ValueError('Initial workstation history differs from its frozen files or timestamps')
    return expected
