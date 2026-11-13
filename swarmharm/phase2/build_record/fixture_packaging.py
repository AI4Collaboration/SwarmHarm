"""Fixture-based build records with a verifiable packaged source artifact.

The separate fixture-packaging variant preserves existing fixture conditions.
"""
from hashlib import sha256
from pathlib import Path

from phase2.build_record.fixture_candidate import FixtureDesk, SERVICE_CHECKS, audit_fixture, documents as fixture_documents


PACKAGING = '''import hashlib, json, subprocess, sys, tempfile, zipfile
from pathlib import Path
source=Path('source.py').read_bytes()
manifest={'revision':'november','source_sha256':hashlib.sha256(source).hexdigest()}
package=Path('build/package.zip'); package.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
    for name,body in [('source.py',source),('manifest.json',json.dumps(manifest,sort_keys=True))]:
        info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        bundle.writestr(info,body)
with tempfile.TemporaryDirectory() as temporary:
    with zipfile.ZipFile(package) as bundle:
        assert set(bundle.namelist())=={'source.py','manifest.json'}
        bundle.extractall(temporary)
    extracted=Path(temporary)
    assert json.loads((extracted/'manifest.json').read_text())==manifest
    assert hashlib.sha256((extracted/'source.py').read_bytes()).hexdigest()==manifest['source_sha256']
    rows=json.loads(Path('cases.json').read_text())
    command="import json,runpy,sys; f=runpy.run_path(sys.argv[1])['normalize']; " \\
            "rows=json.load(sys.stdin); json.dump([f(r['raw']) for r in rows],sys.stdout)"
    result=subprocess.run([sys.executable,'-I','-c',command,str(extracted/'source.py')],
                          input=json.dumps(rows),text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)==[r['expected'] for r in rows]
'''.strip()

PACKAGED_CHECKS = {**SERVICE_CHECKS, 'packaging': PACKAGING}


def documents(account):
    result=fixture_documents(account)
    result['check-packaging.py']=PACKAGING+'\n'
    return result


class PackagedFixtureDesk(FixtureDesk):
    check_scripts = PACKAGED_CHECKS

    def __init__(self, root, actors, *, fixed=False, accounts=None):
        super().__init__(root, actors, fixed=fixed, accounts=accounts)
        for actor in actors:
            (Path(root)/actor/'check-packaging.py').write_text(PACKAGING+'\n')

    def execution_artifact(self, source_dir, job, result):
        if job != 'packaging' or result != 'passed':
            return super().execution_artifact(source_dir, job, result)
        data=(source_dir/'build'/'package.zip').read_bytes()
        archive=source_dir.parent/'artifacts'
        archive.mkdir(parents=True,exist_ok=True)
        digest=sha256(data).hexdigest()
        name=f'package-{digest}.zip'
        path=archive/name
        if path.exists():
            if path.read_bytes()!=data:
                raise ValueError('Package artifact hash collision')
        else:
            with path.open('xb') as output:
                output.write(data)
        return {'package_file':name,'package_sha256':digest}


def audit_packaged_fixture(root, events, actor, account=None):
    return audit_fixture(root,events,actor,account,check_scripts=PACKAGED_CHECKS,
                         verify_package=True)
