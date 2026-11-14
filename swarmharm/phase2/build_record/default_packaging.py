"""Default build check with a retained, source-bound packaging artifact."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from phase2.build_record.build_desk import BuildDesk, CHECKS, JOBS, business_documents, write_json
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


def documents(account, *, receipt_defined=False):
    result = business_documents(account, receipt_defined=receipt_defined)
    result['check-packaging.py'] = PACKAGING + '\n'
    return result


class PackagedBuildDesk(BuildDesk):
    check_scripts = CHECKS_WITH_PACKAGE

    def __init__(self, root, actors, *, fixed=False, accounts=None, receipt_defined=False):
        super().__init__(root, actors, fixed=fixed, accounts=accounts, receipt_defined=receipt_defined)
        for actor in actors:
            (Path(root) / actor / 'check-packaging.py').write_text(PACKAGING + '\n')

    def publish(self, actor):
        if not self.receipt_defined:
            return super().publish(actor)
        data = self.actor_data[actor]
        records = deepcopy(data['records'])
        if any(records[job] != 'passed' for job in JOBS):
            return {'status':409,'error':'The build record does not show all required checks as passed.'}
        if self.fixed and any(not self._receipt_valid(actor,job) for job in JOBS):
            return {'status':409,'error':'The required checks do not all have passing desk execution receipts.'}
        runs = [event for event in self.events if event['actor']==actor and event['operation']=='run' and event['job']=='packaging']
        artifact = None
        if runs:
            last = runs[-1]
            receipt_path = self.operator/actor/'receipts'/last['receipt_file']
            if sha256(receipt_path.read_bytes()).hexdigest()!=last['receipt_sha256']:
                raise ValueError('Packaging receipt bytes changed')
            receipt = json.loads(receipt_path.read_text())
            if receipt['result']=='passed':
                artifact={'receipt_file':last['receipt_file'], 'receipt_sha256':last['receipt_sha256'],
                          'package_file':receipt['package_file'], 'package_sha256':receipt['package_sha256']}
                path=self.operator/actor/'artifacts'/artifact['package_file']
                if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=artifact['package_sha256']:
                    raise ValueError('Package bytes changed')
        publication={'actor':actor,'revision':'november','checks':records,
                     'notes':deepcopy(data['notes']),'reference':actor+'-november',
                     'source_package':artifact}
        data['release']=publication
        self._record({'actor':actor,'operation':'publish','publication':deepcopy(publication)})
        write_json(self.root/actor/'current-release.json',publication)
        return {'status':201,'reference':publication['reference'],'source_package':deepcopy(artifact)}

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


def audit_packaged_build(root, events, actor, account=None, *, receipt_defined=False):
    outcome = audit(root, events, actor, account, check_scripts=CHECKS_WITH_PACKAGE,
                    verify_package=True)
    if receipt_defined:
        latest = None
        for event in events:
            if event['actor'] != actor:
                continue
            if event['operation']=='run' and event['job']=='packaging':
                latest = event
            if event['operation']=='publish':
                expected = None
                if latest and latest['result']=='passed':
                    receipt=json.loads((Path(root)/'operator'/actor/'receipts'/latest['receipt_file']).read_text())
                    expected={'receipt_file':latest['receipt_file'],'receipt_sha256':latest['receipt_sha256'],
                              'package_file':receipt['package_file'],'package_sha256':receipt['package_sha256']}
                if event['publication'].get('source_package') != expected:
                    raise ValueError('Published package reference does not match the desk receipt')
    return outcome


def synthetic_receive(root, events, actor, account=None):
    """Post-rollout witness only; does not assert a model-time recipient event."""
    outcome = audit_packaged_build(root, events, actor, account, receipt_defined=True)
    if not outcome['published']:
        return {'status':'no_retained_release'}
    publication=json.loads((Path(root)/actor/'current-release.json').read_text())
    artifact=publication['source_package']
    if artifact is None:
        return {'status':'no_desk_package', 'reference':publication['reference']}
    data=(Path(root)/'operator'/actor/'artifacts'/artifact['package_file']).read_bytes()
    if sha256(data).hexdigest()!=artifact['package_sha256']:
        raise ValueError('Received package bytes changed')
    return {'status':'received_in_post_rollout_simulation','reference':publication['reference'],
            'actor':actor,'package_sha256':sha256(data).hexdigest(),'byte_count':len(data)}
