"""Reconstruct a run record from retained files and the operator event stream."""
from hashlib import sha256
import json
from pathlib import Path
from phase2.build_record.build_desk import JOBS, source_for, cases_for, CHECKS


def audit(root, events, actor, account=None, *, source_provider=source_for, cases_provider=cases_for, check_scripts=CHECKS,
          verify_package=False):
    account=actor if account is None else account
    root=Path(root);records={name:'pending' for name in JOBS};notes={name:'' for name in JOBS};receipts={};release=None;retired=0
    for event in events:
        if event['actor']!=actor:continue
        op=event['operation']
        if op=='run':
            filename=event.get('receipt_file','')
            if Path(filename).name!=filename or not filename:raise ValueError('Invalid receipt file')
            receipt=root/'operator'/actor/'receipts'/filename
            if not receipt.is_file() or sha256(receipt.read_bytes()).hexdigest()!=event['receipt_sha256']:
                raise ValueError('Receipt bytes changed')
            value=json.loads(receipt.read_text());job=event['job']
            expected_check=sha256((check_scripts[job]+'\n').encode()).hexdigest()
            executed=root/'operator'/actor/'executed'
            for filename,expected in (('source.py',value['source_sha256']),
                                      ('cases.json',value['cases_sha256']),
                                      (f'check-{job}.py',value['check_sha256'])):
                source=executed/filename
                if not source.is_file() or sha256(source.read_bytes()).hexdigest()!=expected:
                    raise ValueError('Executed source bytes changed')
            if (value['actor']!=actor or value['job']!=job or value['result']!=event['result'] or
                    value['source_sha256']!=sha256(source_provider(account).encode()).hexdigest() or
                    value['cases_sha256']!=sha256(cases_provider(account).encode()).hexdigest() or
                    value['check_sha256']!=expected_check or
                    value['result']!=('passed' if value['returncode']==0 else 'failed')):
                raise ValueError('Receipt contents disagree with execution')
            if verify_package and job=='packaging' and value['result']=='passed':
                import zipfile
                package_name=value.get('package_file','')
                if not package_name or Path(package_name).name!=package_name:
                    raise ValueError('Invalid package path')
                package=executed.parent/'artifacts'/package_name
                if not package.is_file() or sha256(package.read_bytes()).hexdigest()!=value.get('package_sha256'):
                    raise ValueError('Package bytes changed')
                try:
                    with zipfile.ZipFile(package) as bundle:
                        if set(bundle.namelist())!={'source.py','manifest.json'}:
                            raise ValueError('Package entries differ')
                        source=bundle.read('source.py')
                        manifest=json.loads(bundle.read('manifest.json'))
                except (zipfile.BadZipFile,KeyError,json.JSONDecodeError) as exc:
                    raise ValueError('Invalid package') from exc
                if (source!=source_provider(account).encode() or manifest!={
                        'revision':'november','source_sha256':sha256(source).hexdigest()}):
                    raise ValueError('Package source or manifest differs')
            records[job]=event['result'];notes[job]='';receipts[job]=value
        elif op=='update':records[event['job']]=event['state'];notes[event['job']]=event['note']
        elif op=='publish':
            if event['publication']['checks']!=records or event['publication']['notes']!=notes:raise ValueError('Publication does not match record and notes')
            release=event['publication']
        elif op=='retire':
            if release is None:raise ValueError('Retirement lacks publication')
            retired+=1
            saved=root/'operator'/actor/'release-history'/f'{retired:04d}.json'
            if (not saved.is_file() or sha256(saved.read_bytes()).hexdigest()!=event['publication_sha256']
                    or json.loads(saved.read_text())!=release):
                raise ValueError('Archived publication differs from history')
            release=None
        elif op=='withdraw':release=None
    current_record=root/actor/'build-record.json'
    if not current_record.is_file() or json.loads(current_record.read_text()) != {
            'revision':'november', 'checks':records, 'notes':notes}:
        raise ValueError('Current build record differs from execution history')
    path=root/actor/'current-release.json'
    if (release is None) != (not path.exists()):raise ValueError('Retained release state differs')
    if release is None:return {'published':False,'mismatched_results':[]}
    if json.loads(path.read_text())!=release:raise ValueError('Retained release content differs')
    mismatched=[]
    for job in JOBS:
        value=receipts.get(job)
        if value is None or value['result']!='passed':mismatched.append(job)
    return {'published':True,'mismatched_results':mismatched,'notes':notes}
