"""Build-time only: install pinned GCC cases named by the upstream public filter."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json, urllib.request, hashlib
base=Path('/app/tests/gcc/gcc/testsuite/gcc.c-torture/execute');base.mkdir(parents=True,exist_ok=True)
commit='63fc48f077cbd03ddc779b079e93c8e5d5ce1098'
names=json.loads(Path('/app/filter.json').read_text())['gcc_torture']
def fetch(name):
    path=name+'.c'; url=f'https://raw.githubusercontent.com/gcc-mirror/gcc/{commit}/gcc/testsuite/gcc.c-torture/execute/{path}'
    data=urllib.request.urlopen(url,timeout=90).read();(base/path).write_bytes(data)
    return {'path':path,'sha256':hashlib.sha256(data).hexdigest()}
with ThreadPoolExecutor(max_workers=8) as pool: rows=list(pool.map(fetch,names))
Path('/app/gcc-source-manifest.json').write_text(json.dumps({'commit':commit,'files':rows},indent=2))
