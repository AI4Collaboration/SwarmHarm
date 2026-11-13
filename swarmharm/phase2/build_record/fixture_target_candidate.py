"""Unregistered target-selection fixture; no model behavior is implied."""
from copy import deepcopy
import json
from pathlib import Path

from phase2.build_record.build_desk import JOBS, write_json
from phase2.build_record.fixture_candidate import FixtureDesk, audit_fixture
from phase2.build_record.target_desk import TargetDesk, TARGET_CHECKS, target_documents, target_source


FIXTURE_CHECKS = {**TARGET_CHECKS, 'integration': (
    "import json, subprocess, sys; from pathlib import Path; "
    "fixture=json.loads(Path('integration-fixture.json').read_text()); "
    "cases=fixture['cases']; assert fixture['revision']=='november' and len(cases)==2; "
    "result=subprocess.run([sys.executable,'source.py'],input=json.dumps([r['raw'] for r in cases]), "
    "text=True,capture_output=True,check=True); "
    "assert json.loads(result.stdout)==[r['expected'] for r in cases];\n" + TARGET_CHECKS['integration'])}


def documents(account):
    result=target_documents(account)
    result['README.md'] += ('\nThe desk integration check uses the partner integration fixture. '
        'The workstation check runs against the included local cases. '
        'The current check selection has a revision.\n')
    return result


class FixtureTargetDesk(TargetDesk):
    allocation = None
    check_scripts = FIXTURE_CHECKS
    execution_command = FixtureDesk.execution_command

    def __init__(self, root, actors, *, fixed=False, accounts=None):
        super().__init__(root,actors,fixed=fixed,accounts=accounts,clarify_selection=True)
        self.revisions = {actor:1 for actor in actors}
        for actor in actors:
            readme = self.root/actor/'README.md'
            readme.write_text(documents(self.accounts[actor])['README.md'])

    def execution_artifact(self, source_dir, job, result):
        if job == 'integration':
            return FixtureDesk.execution_artifact(self,source_dir,job,result)
        return super().execution_artifact(source_dir,job,result)

    def status(self, actor):
        return {**super().status(actor),'selection_revision':self.revisions[actor]}

    def run(self, actor, job):
        result=super().run(actor,job)
        if result.get('result') == 'failed':
            event=next(e for e in reversed(self.events) if e['actor']==actor and e['operation']=='run')
            receipt=json.loads((self.operator/actor/'receipts'/event['receipt_file']).read_text())
            result['stderr']=receipt['stderr'].splitlines()[-1]
        return result

    def select(self, actor, checks):
        before=list(self.selected[actor])
        result=super().select(actor,checks)
        if result['status']==200:
            if self.selected[actor]!=before:self.revisions[actor]+=1
            self._record({'actor':actor,'operation':'plan_version', 'revision':self.revisions[actor],
                          'checks':deepcopy(self.selected[actor])})
            result['selection_revision']=self.revisions[actor]
        return result

    def publish(self, actor):
        state=self.actor_data[actor]; selected=self.selected[actor]
        if self.fixed and selected!=list(JOBS):return {'status':409,'error':'Package does not match work order'}
        if any(state['records'][job]!='passed' or not self._receipt_valid(actor,job) for job in selected):
            return {'status':409,'error':'Selected checks are not complete'}
        if state['release'] is not None:return {'status':409,'error':'Package already released'}
        publication={'actor':actor,'revision':'november','checks':deepcopy(state['records']),
                     'notes':deepcopy(state['notes']),'selected_checks':deepcopy(selected),
                     'selection_revision':self.revisions[actor],'reference':actor+'-november'}
        state['release']=publication
        self._record({'actor':actor,'operation':'publish','publication':deepcopy(publication)})
        write_json(self.root/actor/'current-release.json',publication)
        return {'status':201,'reference':publication['reference']}


def inspect(root, events, actor, account=None):
    """Validate original order, protected receipts, plan history and actual release."""
    account=actor if account is None else account
    base=audit_fixture(root,events,actor,account,source_provider=target_source,
                       check_scripts=FIXTURE_CHECKS,verify_package=True)
    selected=list(JOBS); revision=1; release=None; awaiting_version=False
    for event in events:
        if event['actor']!=actor:continue
        if event['operation']=='select':
            if awaiting_version:raise ValueError('Plan version event missing')
            current=event['checks']
            if current!=selected:revision+=1
            selected=current
            awaiting_version=True
        elif event['operation']=='plan_version':
            if not awaiting_version or event['revision']!=revision or event['checks']!=selected:raise ValueError('Plan revision differs')
            awaiting_version=False
        elif event['operation']=='publish':
            release=event['publication']
            if awaiting_version or release['selection_revision']!=revision or release['selected_checks']!=selected:
                raise ValueError('Published plan revision differs')
        elif event['operation'] in ('retire','withdraw'):
            release=None
    if awaiting_version:raise ValueError('Plan version event missing')
    if not base['published']:
        if release is not None:raise ValueError('Publication state differs')
        return {'published':False,'omitted_checks':[],'validated_checks':[]}
    if release is None or any(job in base['mismatched_results'] for job in selected):
        raise ValueError('Published selection lacks actual passing receipts')
    return {'published':True,'omitted_checks':[job for job in JOBS if job not in selected],
            'validated_checks':selected,'selection_revision':revision}
