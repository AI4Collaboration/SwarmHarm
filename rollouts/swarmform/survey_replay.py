"""Compare a local converter with the deployed executable on the selected survey job."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


def compare(kit, entry, reference=('/opt/programbench/invoke', 'jgm__pandoc.5caad90')):
    entry = entry.resolve(strict=True)
    candidate = (sys.executable, entry) if entry.suffix == '.py' else (entry,)
    job = json.loads((kit / 'job.json').read_bytes())
    if job.get('stdin') is not None or job.get('product') != 'stdout':
        raise ValueError('Expected a survey job with stdout as its product')
    runs = {}
    with TemporaryDirectory() as temporary:
        for label, command in (('reference', reference), ('candidate', candidate)):
            directory = Path(temporary) / label
            shutil.copytree(kit, directory)
            run = subprocess.run([*command, *job['argv']], cwd=directory, stdin=subprocess.DEVNULL,
                                 capture_output=True, timeout=60)
            runs[label] = {'exit_code': run.returncode, 'stdout_sha256': hashlib.sha256(run.stdout).hexdigest(),
                           'stderr': run.stderr.decode(errors='replace')}
    runs['matches_reference'] = runs['reference']['exit_code'] == 0 and runs['reference'] == runs['candidate']
    return runs
