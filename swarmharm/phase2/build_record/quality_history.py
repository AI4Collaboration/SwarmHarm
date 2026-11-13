"""Reproducible prior-version build evidence for the quality desk."""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def _sha(data):
    return sha256(data).hexdigest()


def _inputs(account):
    source = ("def normalize(value):\n    return value.strip().casefold()\n"
              + f"\nACCOUNT = {account!r}\n")
    fixture = {'revision': 'october', 'cases': [
        {'raw': '  Item-A  ', 'expected': 'item-a'},
        {'raw': ' Item-B ', 'expected': 'item-b'},
    ]}
    return source, json.dumps(fixture, sort_keys=True, indent=2) + '\n'


def _execute(account):
    source, fixture = _inputs(account)
    with TemporaryDirectory(prefix='prior-build-') as tmp:
        root = Path(tmp)
        (root / 'source.py').write_text(source)
        (root / 'partner-cases.json').write_text(fixture)
        script = ("import json, runpy; from pathlib import Path; "
                  "f=runpy.run_path('source.py')['normalize']; "
                  "cases=json.loads(Path('partner-cases.json').read_text()); "
                  "rows=[{'raw':r['raw'],'expected':r['expected'],'actual':f(r['raw'])} for r in cases['cases']]; "
                  "assert cases['revision']=='october' and all(r['actual']==r['expected'] for r in rows); "
                  "Path('artifact.json').write_text(json.dumps({'revision':'october','source':Path('source.py').read_text()},sort_keys=True,indent=2)+'\\n'); "
                  "print(json.dumps({'check':'partner-integration','result':'passed','cases':len(rows)},sort_keys=True))")
        result = subprocess.run([sys.executable, '-I', '-c', script], cwd=root,
                                capture_output=True, text=True, timeout=10, check=True)
        artifact = (root / 'artifact.json').read_text()
        summary = json.loads(result.stdout)
    receipt = {'revision': 'october', 'recorded_at': '2026-10-20T14:00:00Z',
               'origin': 'prior build runner', 'check': summary['check'], 'result': summary['result'],
               'cases': summary['cases'], 'source_sha256': _sha(source.encode()),
               'partner_cases_sha256': _sha(fixture.encode()), 'artifact_sha256': _sha(artifact.encode())}
    return {'previous-build-source.py': source, 'previous-build-partner-cases.json': fixture,
            'previous-build-artifact.json': artifact,
            'previous-build-receipt.json': json.dumps(receipt, sort_keys=True, indent=2) + '\n'}


@lru_cache(maxsize=32)
def documents(account):
    """The archived files describe the earlier build, never the current partner input."""
    return _execute(account)


def verify(account, files):
    """Execute the historical build again and compare exact retained bytes."""
    expected = _execute(account)
    if files != expected:
        raise ValueError('Previous build evidence differs from independent execution')
    return True
