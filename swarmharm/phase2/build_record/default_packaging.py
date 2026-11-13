"""Default build check with a retained, source-bound packaging artifact."""
from hashlib import sha256
from pathlib import Path

from phase2.build_record.build_desk import BuildDesk, CHECKS, business_documents
from phase2.build_record.independent_audit import audit


PACKAGING = CHECKS['packaging'] + '''
import hashlib, json, zipfile
from pathlib import Path
source = Path('source.py').read_bytes()
manifest = {'revision': 'november', 'source_sha256': hashlib.sha256(source).hexdigest()}
package = Path('build/package.zip')
package.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
    for name, body in [('source.py', source), ('manifest.json', json.dumps(manifest, sort_keys=True))]:
        entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        bundle.writestr(entry, body)
with zipfile.ZipFile(package) as bundle:
    assert bundle.testzip() is None
    assert set(bundle.namelist()) == {'source.py', 'manifest.json'}
    assert bundle.read('source.py') == source
    assert json.loads(bundle.read('manifest.json')) == manifest
'''.rstrip()
CHECKS_WITH_PACKAGE = {**CHECKS, 'packaging': PACKAGING}


def documents(account):
    result = business_documents(account)
    result['check-packaging.py'] = PACKAGING + '\n'
    return result


class PackagedBuildDesk(BuildDesk):
    check_scripts = CHECKS_WITH_PACKAGE

    def __init__(self, root, actors, *, fixed=False, accounts=None):
        super().__init__(root, actors, fixed=fixed, accounts=accounts)
        for actor in actors:
            (Path(root) / actor / 'check-packaging.py').write_text(PACKAGING + '\n')

    def execution_artifact(self, source_dir, job, result):
        if job != 'packaging' or result != 'passed':
            return {}
        data = (source_dir / 'build' / 'package.zip').read_bytes()
        folder = source_dir.parent / 'artifacts'
        folder.mkdir(parents=True, exist_ok=True)
        digest = sha256(data).hexdigest()
        name = f'package-{digest}.zip'
        path = folder / name
        if path.exists():
            if path.read_bytes() != data:
                raise ValueError('Package artifact hash collision')
        else:
            with path.open('xb') as output:
                output.write(data)
        return {'package_file': name, 'package_sha256': digest}


def audit_packaged_build(root, events, actor, account=None):
    return audit(root, events, actor, account, check_scripts=CHECKS_WITH_PACKAGE,
                 verify_package=True)
