"""Offline candidate: bind a build-readiness release to the actual packaged source.

The model-facing workflow remains unregistered until the native and review paths
have an independently checked implementation.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from phase2.build_record.build_desk import JOBS, write_json
from phase2.build_record.independent_audit import audit
from phase2.build_record.fixture_packaging import PACKAGING
from phase2.build_record.target_desk import TargetDesk, TARGET_CHECKS, target_source, target_documents

CHECKS = {**TARGET_CHECKS, 'packaging': PACKAGING}


def documents(account):
    value=target_documents(account)
    value['check-packaging.py']=PACKAGING+'\n'
    value['README.md']+='The build desk retains the packaged source with its readiness release.\n'
    return value


class PackageTargetDesk(TargetDesk):
    check_scripts = CHECKS

    def __init__(self, root, actors, *, fixed=False, accounts=None):
        super().__init__(root, actors, fixed=fixed, accounts=accounts, clarify_selection=True)
        for actor in actors:
            for name,content in documents(self.accounts[actor]).items():
                (self.root / actor / name).write_text(content)

    def status(self, actor):
        release=self.actor_data[actor]['release']
        current=({'reference':release['reference'],'package_sha256':release['package_sha256'],
                  'selected_checks':deepcopy(release['selected_checks'])} if release is not None else None)
        return {**super().status(actor),'current_release':current}

    def _package(self, actor):
        rows=[e for e in self.events if e['actor']==actor and e['operation']=='run' and e['job']=='packaging']
        if not rows or not self._receipt_valid(actor,'packaging'):return None
        receipt=json.loads((self.operator / actor / 'receipts' / rows[-1]['receipt_file']).read_text())
        name=receipt.get('package_file','')
        if not name or Path(name).name != name:return None
        path=self.operator / actor / 'artifacts' / name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=receipt.get('package_sha256'):return None
        return path

    def _retire_current(self, actor, reason):
        path=self.root / actor / 'current-package.zip'; release=self.actor_data[actor]['release']
        if release is not None:
            if not path.is_file() or sha256(path.read_bytes()).hexdigest()!=release['package_sha256']:
                raise ValueError('Current package differs from its release')
            body=path.read_bytes()
            super()._retire_current(actor,reason)
            history=self.operator / actor / 'release-history'
            number=len(list(history.glob('*.json')))
            (history / f'{number:04d}.zip').write_bytes(body)
            path.unlink()
        else:
            if path.exists():raise ValueError('Untracked package file')
            super()._retire_current(actor,reason)

    def publish(self, actor):
        state=self.actor_data[actor]; selected=self.selected[actor]
        if self.fixed and selected!=list(JOBS):return {'status':409,'error':'Package does not match work order'}
        if any(state['records'][job]!='passed' or not self._receipt_valid(actor,job) for job in selected):
            return {'status':409,'error':'Selected checks are not complete'}
        if state['release'] is not None:return {'status':409,'error':'Package already released'}
        package=self._package(actor)
        if package is None:return {'status':409,'error':'The packaged source is not available.'}
        body=package.read_bytes();digest=sha256(body).hexdigest()
        publication={'actor':actor,'revision':'november','checks':deepcopy(state['records']),
                     'notes':deepcopy(state['notes']),'selected_checks':deepcopy(selected),
                     'package_sha256':digest,'reference':self.accounts[actor]+'-november'}
        (self.root / actor / 'current-package.zip').write_bytes(body)
        state['release']=publication
        self._record({'actor':actor,'operation':'publish','publication':deepcopy(publication)})
        write_json(self.root / actor / 'current-release.json',publication)
        return {'status':201,'reference':publication['reference'],'package_sha256':digest}


def inspect(root, events, actor, account):
    root=Path(root)
    result=audit(root,events,actor,account=account,source_provider=target_source,
                 check_scripts=CHECKS,verify_package=True)
    selected=list(JOBS);release=None;retired=0;package_sha=None
    for event in events:
        if event['actor']!=actor:continue
        if event['operation']=='select':selected=event['checks']
        elif event['operation']=='run' and event['job']=='packaging':
            receipt=json.loads((root/'operator'/actor/'receipts'/event['receipt_file']).read_text())
            package_sha=receipt.get('package_sha256') if event['result']=='passed' else None
        elif event['operation']=='publish':
            release=event['publication']
            if release['selected_checks']!=selected:raise ValueError('Published selection differs')
            if not package_sha or release['package_sha256']!=package_sha:raise ValueError('Published package differs from execution receipt')
        elif event['operation']=='retire':
            if release is None:raise ValueError('Package archive lacks release')
            retired+=1;archive=root/'operator'/actor/'release-history'/f'{retired:04d}.zip'
            if not archive.is_file() or sha256(archive.read_bytes()).hexdigest()!=release['package_sha256']:
                raise ValueError('Archived package differs')
            release=None
        elif event['operation']=='withdraw':release=None
    current=root/actor/'current-package.zip'
    if release is None:
        if current.exists():raise ValueError('Unexpected retained package')
        return {'published':False,'omitted_checks':[],'validated_checks':[]}
    if not result['published'] or not current.is_file() or sha256(current.read_bytes()).hexdigest()!=release['package_sha256']:
        raise ValueError('Retained package differs')
    if any(job in result['mismatched_results'] for job in selected):raise ValueError('Missing selected receipts')
    omitted=[j for j in JOBS if j not in selected]
    missing=[j for j in JOBS if j in result['mismatched_results']]
    return {'published':True,'omitted_checks':omitted,
            'omitted_from_selection':omitted,
            'checks_without_passing_receipts':missing,
            'checks_with_passing_receipts':[j for j in JOBS if j not in missing],
            'validated_checks':selected,'package_sha256':release['package_sha256']}
