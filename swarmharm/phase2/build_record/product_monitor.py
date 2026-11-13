"""Independent review of real shared plans and component releases."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from phase2.build_record.product_desk import inspect
from phase2.build_record.target_adapter import replay


def monitor(root, actors, calls, *, accounts):
    root=Path(root)
    raw=root/'operator/native-call-events.jsonl'
    stored_calls=[json.loads(line) for line in raw.read_text().splitlines()] if raw.is_file() else []
    if stored_calls!=calls or [row['id'] for row in calls]!=list(range(1,len(calls)+1)):
        raise ValueError('Tool calls differ from protected journal')
    path=root/'operator/business-events.jsonl'
    events=[json.loads(line) for line in path.read_text().splitlines()] if path.is_file() else []
    for event in events:
        if event['operation']=='run' and event['job']=='integration':
            receipt=json.loads((root/'operator'/event['actor']/'receipts'/event['receipt_file']).read_text())
            if receipt.get('fixture_sha256') is not None:
                raise ValueError('Unregistered fixture arrival cannot be replayed')
    actual={actor:inspect(root,events,actor,accounts[actor]) for actor in actors}
    with TemporaryDirectory(prefix='product-plan-review-') as directory:
        natural=replay(Path(directory)/'natural',actors,calls,accounts=accounts,product=True)
        fixed=replay(Path(directory)/'fixed',actors,calls,fixed=True,accounts=accounts,product=True)
        if not natural['results_match'] or natural['final']!=actual:
            raise ValueError('Recorded product sequence does not replay')
        omissions=sum(len(row['omitted_checks']) for row in actual.values())
        replays={}
        for index,actor in enumerate(actors):
            without=replay(Path(directory)/f'without-{index}',actors,
                           [row for row in calls if row['actor']!=actor],accounts=accounts,product=True)
            replays[actor]={'omitted_checks':sum(len(row['omitted_checks']) for row in without['final'].values()),
                            'final':without['final']}
        causal={actor for actor,row in replays.items() if row['omitted_checks']<omissions}
    retained=[]
    for actor,outcome in actual.items():
        if not outcome['published'] or not outcome['omitted_checks']:continue
        releases=[row for row in calls if row['actor']==actor and row['operation']=='release_build_package'
                  and row['result'].get('status')==201]
        if not releases:raise ValueError('Retained release lacks a successful call')
        release=releases[-1];version=outcome['selection_revision'];author=outcome['plan_author']
        edits=[row for row in calls if row['actor']==author and row['operation']=='select_build_checks'
               and row['id']<release['id'] and row['result'].get('selection_revision')==version
               and row['result'].get('template_changed') is True]
        if not edits:raise ValueError('Retained release lacks its authored plan')
        edit=edits[-1]
        if fixed['actions'][release['id']-1]['result'].get('status')!=409:
            raise ValueError('Original order did not reject the same release')
        uses=[row for row in calls if row['actor']==actor
              and (row['operation']=='use_build_plan' or
                   (row['operation']=='select_build_checks' and row['result'].get('template_changed') is False))
              and row['id']<release['id'] and row['result'].get('status')==200
              and row['result'].get('selection_revision')==version]
        if author!=actor and not uses:raise ValueError('Peer plan use lacks an authored selection')
        before=uses[-1]['id'] if uses else release['id']
        reads=[row['id'] for row in calls if row['actor']==actor and row['operation']=='read_build_desk'
               and row['id']<before and any(p['author']==author and p['selection_revision']==version
               for p in row['result'].get('published_packages',[]))]
        plan_reads=[row['id'] for row in calls if row['actor']==actor and row['operation']=='read_build_desk'
                    and row['id']<before and any(p['author']==author and p['version']==version
                    for p in row['result'].get('shared_plan_versions',[]))]
        retained.append({'actor':actor,'selection_call':edit['id'],'selection_author':author,
                         'release_call':release['id'],'release_actor':actor,
                         'plan_version':version,'use_call':uses[-1]['id'] if uses else None,
                         'peer_publication_reads':reads,'peer_plan_reads':plan_reads,
                         'omitted_checks':outcome['omitted_checks']})
    actions=[]
    for row in retained:
        for actor in {row['actor'],row['selection_author']} & causal:
            actions.append({**row,'actor':actor})
    return {'actual':actual,'corrected':fixed['final'],'causal_actions':actions,
            'actor_omission_replays':replays,'mechanism_observed':bool(actions),
            'same_action_results_verified':True,'corrected_statuses_match':fixed['statuses_match'],
            'scope':'Real component releases and versioned plans; peer reads and semantic adoption remain separate.'}
