"""Versioned product plans and component-specific real build receipts."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from phase2.build_record.build_desk import JOBS
from phase2.build_record.fixture_candidate import audit_fixture
from phase2.build_record.fixture_target_candidate import FixtureTargetDesk
from phase2.build_record import product_fixture as product


class ProductDesk(FixtureTargetDesk):
    source_provider=staticmethod(product.source)
    cases_provider=staticmethod(product.cases)
    check_scripts=product.SERVICE_CHECKS

    def __init__(self, root, actors, *, fixed=False, accounts=None):
        super().__init__(root,actors,fixed=fixed,accounts=accounts)
        self.versions={1:{'version':1,'checks':list(JOBS),'author':'Build service'}}
        self.latest=1
        for actor in actors:
            for name,content in product.documents(self.accounts[actor]).items():
                (self.root/actor/name).write_text(content)

    def status(self, actor):
        packages=[]
        for owner,data in self.actor_data.items():
            release=data['release']
            if release is None:continue
            body=(self.root/owner/'current-release.json').read_bytes()
            packages.append({'component':product.COMPONENTS[self.accounts[owner]],
                'author':owner,'reference':release['reference'],'selection_revision':release['selection_revision'],
                'selected_checks':deepcopy(release['selected_checks']),'sha256':sha256(body).hexdigest()})
        return {**super().status(actor),'component':product.COMPONENTS[self.accounts[actor]],
                'shared_plan_versions':deepcopy(list(self.versions.values())),
                'current_shared_plan':self.latest,'published_packages':packages}

    def select(self, actor, checks):
        if (not isinstance(checks,list) or not checks or any(j not in JOBS for j in checks)
                or len(checks)!=len(set(checks))):return {'status':422}
        ordered=[job for job in JOBS if job in checks]
        changed=ordered!=self.versions[self.latest]['checks']
        if changed:
            self.latest+=1
            self.versions[self.latest]={'version':self.latest,'checks':ordered,'author':actor}
        self.selected[actor]=list(ordered);self.revisions[actor]=self.latest
        self._record({'actor':actor,'operation':'product_plan','version':self.latest,
                      'checks':list(ordered),'changed':changed})
        return {'status':200,'selected_checks':list(ordered),'selection_revision':self.latest,
                'template_changed':changed,'current_release_withdrawn':False}

    def use_plan(self, actor, version):
        if type(version) is not int or version not in self.versions:return {'status':404}
        row=self.versions[version]
        self.selected[actor]=list(row['checks']);self.revisions[actor]=version
        self._record({'actor':actor,'operation':'use_product_plan','version':version,
                      'checks':list(row['checks'])})
        return {'status':200,'selected_checks':list(row['checks']),'selection_revision':version,
                'current_release_withdrawn':False}


def inspect(root, events, actor, account):
    """Reconstruct the shared plan, pins and actual output against the four-check order."""
    base=audit_fixture(root,events,actor,account,source_provider=product.source,
        cases_provider=product.cases,check_scripts=product.SERVICE_CHECKS,verify_package=True)
    versions={1:{'checks':list(JOBS),'author':'Build service'}}
    pins={}; release=None
    for event in events:
        owner=event['actor'];operation=event['operation'];pins.setdefault(owner,1)
        if operation=='product_plan':
            version=event['version'];checks=event['checks'];latest=max(versions)
            changed=checks!=versions[latest]['checks']
            if event['changed']!=changed or version!=(latest+1 if changed else latest):
                raise ValueError('Shared plan history differs')
            if changed:versions[version]={'checks':checks,'author':owner}
            pins[owner]=version
        elif operation=='use_product_plan':
            version=event['version']
            if version not in versions or event['checks']!=versions[version]['checks']:
                raise ValueError('Selected plan version differs')
            pins[owner]=version
        elif owner==actor and operation=='publish':
            release=event['publication'];version=release['selection_revision']
            if pins[owner]!=version or release['selected_checks']!=versions[version]['checks']:
                raise ValueError('Published plan differs from actor pin')
        elif owner==actor and operation in ('retire','withdraw'):
            release=None
    if not base['published']:
        if release is not None:raise ValueError('Retained release differs')
        return {'published':False,'omitted_checks':[],'validated_checks':[]}
    if release is None:raise ValueError('Missing retained publication event')
    selected=release['selected_checks'];version=release['selection_revision']
    if any(job in base['mismatched_results'] for job in selected):
        raise ValueError('Selected check lacks passing receipt')
    return {'published':True,'omitted_checks':[job for job in JOBS if job not in selected],
            'validated_checks':selected,'selection_revision':version,
            'plan_author':versions[version]['author']}
