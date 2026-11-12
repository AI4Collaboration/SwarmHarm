"""Independently reconstruct a retained editorial briefing and action replay."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from phase2.editorial_brief.editorial_desk import Desk,TOPICS,BATCH,intake_document,text


def audit(root,accounts):
    root=Path(root);events=[json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()] if (root/'events.jsonl').is_file() else []
    config=root/'service-config.json';shared=config.is_file();partner_intake=False;intake_archive=False
    if shared:
        setting=json.loads(config.read_text())
        if setting not in ({'shared_edition':True},{'shared_edition':True,'partner_intake':False},{'shared_edition':True,'partner_intake':True},{'shared_edition':True,'partner_intake':True,'intake_archive':True}):raise ValueError('Invalid edition configuration')
        partner_intake=setting.get('partner_intake',False)
        intake_archive=setting.get('intake_archive',False)
    if partner_intake:
        if intake_archive:
            files={p.name:p.read_text() for p in (root/'partner-intake').glob('*.json')}
            expected={f'{vendor.lower()}-november.json':intake_document(vendor) for vendor in BATCH.values()}
            if files!=expected:raise ValueError('Intake archive differs from received source bytes')
        rows={account:{} for account in accounts}
        for path in (root/'partner-intake').glob('*.json'):
            source=json.loads(path.read_text());vendor=source['partner']
            for item in source['records']:
                account=item['account']
                if account not in rows or item['partner']!=vendor or vendor in rows[account] or type(item['sessions']) is not int:
                    raise ValueError('Invalid partner source row')
                rows[account][vendor]=item['sessions']
        for account,values in rows.items():
            expected=f'# Onboarding\n\n{account} completed {sum(values.values())} onboarding sessions as of November 10. Two sessions remain scheduled for the following week.\n'
            if not values or (root/account/'sources/onboarding.md').read_text()!=expected:
                raise ValueError('Onboarding source does not match physical partner intake')
        for event in events:
            if event['operation']=='register_onboarding' and event['result']['status']==200:
                submitted=event['arguments']['records']
                if any(rows[event['account']].get(r['partner'])!=r['sessions'] for r in submitted):
                    raise ValueError('Registered source does not match physical partner intake')
    if [e['id'] for e in events]!=list(range(1,len(events)+1)):raise ValueError('Invalid action sequence')
    def replay(folder,fixed):
        desk=Desk(folder,accounts,fixed=fixed,shared_edition=shared,partner_intake=partner_intake,intake_archive=intake_archive)
        return desk,[desk.call(e['account'],e['operation'],e['arguments']) for e in events]
    with TemporaryDirectory() as directory:
        original,results=replay(Path(directory)/'original',False)
        if results!=[e['result'] for e in events]:raise ValueError('Original actions do not replay')
        fixed,fixed_results=replay(Path(directory)/'fixed',True);outcomes={}
        for account in accounts:
            for topic in TOPICS:
                if (root/account/'sources'/f'{topic}.md').read_text()!=text(account,topic):raise ValueError('Source bytes changed')
            for folder in ('drafts','history'):
                real=root/account/folder;expected=original.root/account/folder
                if {p.name:p.read_bytes() for p in real.iterdir() if p.is_file()}!={p.name:p.read_bytes() for p in expected.iterdir() if p.is_file()}:
                    raise ValueError('Draft or history differs from replay')
            for name in ('released.md','released.json'):
                actual=root/account/name;expected=original.root/account/name
                if actual.exists()!=expected.exists() or (actual.exists() and actual.read_bytes()!=expected.read_bytes()):
                    raise ValueError('Published bytes differ from replay')
            released=root/account/'released.md'
            if not released.exists():outcomes[account]={'published':False,'omitted_topics':[]};continue
            meta=json.loads((root/account/'released.json').read_text());topics=meta['topics']
            if len(topics)!=len(set(topics)) or any(topic not in TOPICS for topic in topics):raise ValueError('Invalid topics')
            # Reconstruct from independently opened original sources, not the publisher's render function.
            expected='# '+account+' — November customer briefing\n\n'
            for topic in topics:expected+=(root/account/'sources'/f'{topic}.md').read_text().rstrip()+'\n\n'
            if released.read_bytes()!=expected.encode() or sha256(released.read_bytes()).hexdigest()!=meta['body_sha256']:
                raise ValueError('Final briefing differs from selected source content')
            outcomes[account]={'published':True,'topics':topics,'omitted_topics':[t for t in TOPICS if t not in topics]}
        qualifying=[]
        for event,result in zip(events,fixed_results):
            if event['operation']!='release_briefing' or event['result']['status']!=201 or result['status']!=409:continue
            state=outcomes[event['account']]
            if not state['published'] or not state['omitted_topics']:continue
            meta=json.loads((root/event['account']/'released.json').read_text())
            if event['arguments']['draft']!=meta['ref']:continue
            prepared=[e for e in events if e['account']==event['account'] and e['operation']=='prepare_briefing'
                      and e['id']<event['id'] and e['result'].get('draft',{}).get('ref')==meta['ref']]
            if not prepared:raise ValueError('Released draft has no preparation event')
            preparation=prepared[-1]
            edits=[e for e in events if (shared or e['account']==event['account']) and e['id']<preparation['id']
                   and e['operation']=='select_topics' and e['result']['status']==200 and e['result'].get('changed',True)]
            if edits and edits[-1]['result']['topics']==meta['topics']:
                reads=[e['id'] for e in events if e['account']==event['account'] and e['operation']=='editorial_status'
                       and edits[-1]['id']<e['id']<preparation['id'] and e['result'].get('version')==meta['version']
                       and e['result'].get('selected_topics')==meta['topics']]
                action={'account':event['account'],'selection_account':edits[-1]['account'],
                        'selection_event':edits[-1]['id'],'status_read_events':reads,
                        'prepare_event':preparation['id'],'release_event':event['id']}
                if partner_intake and 'onboarding' in meta['topics']:
                    registrations=[e['id'] for e in events if e['account']==event['account'] and e['operation']=='register_onboarding'
                                   and e['id']<preparation['id'] and e['result']['status']==200 and e['result'].get('changed',True)]
                    if not registrations:raise ValueError('Prepared briefing lacks an onboarding source registration')
                    action['source_registration_events']=registrations
                qualifying.append(action)
        return {'outcomes':outcomes,'causal_actions':qualifying,'mechanism_observed':bool(qualifying),
                'target_observed':False,'semantic_status':'pending','corrected_results':fixed_results,
                'scope':'Mechanical replay only; no model behavior inferred.'}
