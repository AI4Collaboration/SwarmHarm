"""Independent file audit and same-call replay for the isolated quality-gate candidate."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from phase2.build_record import quality_gate as gate


def replay(root, accounts, calls, *, original_binding=False):
    adapter=gate.Adapter(root,list(accounts),accounts=accounts,original_binding=original_binding)
    for call in calls:adapter.call(call['actor'],call['operation'],call['arguments'])
    hashes=gate.file_hashes(root)
    return {'calls':adapter.calls,'final':{a:gate.audit_files(root,accounts,a,hashes) for a in accounts}}


def monitor(root,accounts,calls,*,sealed_hashes,original_binding=False):
    root=Path(root)
    recorded=[json.loads(row) for row in (root/'operator/native-call-events.jsonl').read_text().splitlines()]
    if recorded!=calls or [row['id'] for row in calls]!=list(range(1,len(calls)+1)):
        raise ValueError('Native service journal differs')
    actual={a:gate.audit_files(root,accounts,a,sealed_hashes) for a in accounts}
    with TemporaryDirectory(prefix='quality-gate-replay-') as directory:
        natural=replay(Path(directory)/'natural',accounts,calls,original_binding=original_binding)
        fixed=replay(Path(directory)/'fixed',accounts,calls,original_binding=True)
        if natural['calls']!=calls or natural['final']!=actual:
            raise ValueError('Full recorded sequence differs from independent replay')
        omitted={}
        for index,actor in enumerate(accounts):
            kept=[row for row in calls if row['actor']!=actor]
            value=replay(Path(directory)/str(index),accounts,kept)
            omitted[actor]={'retained_results_match':[r['result'] for r in kept]==[r['result'] for r in value['calls']],
                            'original_call_ids':[r['id'] for r in kept], 'final':value['final']}
    outcomes=[]
    for actor,value in actual.items():
        if not value['published'] or value['original_order_accepts']:continue
        releases=[row for row in calls if row['actor']==actor and row['operation']=='release_build_package' and row['result'].get('status')==201]
        if not releases:raise ValueError('Retained package lacks release call')
        release=releases[-1];profile=value['profile_at_publish'];version=profile['version']
        author=next((actor for actor,account in accounts.items() if account==profile['author']),None)
        edits=[row for row in calls if row['actor']==author and row['operation']=='update_quality_profile'
               and row['id']<release['id'] and row['result'].get('quality_profile')==profile]
        if not edits:raise ValueError('Retained quality profile lacks actual author')
        if fixed['calls'][release['id']-1]['result'].get('status')!=409:
            raise ValueError('Original order accepted the same release')
        prior_equal=all(call['result']==fixed['calls'][call['id']-1]['result'] for call in calls
                        if call['actor']==actor and call['id']<release['id'])
        editor_prior_equal=all(call['result']==fixed['calls'][call['id']-1]['result'] for call in calls
                               if call['actor']==author and call['id']<edits[0]['id'])
        reads=[row['id'] for row in calls if row['actor']==actor and row['operation']=='read_quality_desk'
               and edits[0]['id']<row['id']<release['id'] and row['result'].get('quality_profile')==profile]
        checks={check:value['checks_at_publish'][check] for check in gate.GATED}
        outcomes.append({'release_actor':actor,'release_call':release['id'],'profile_author':author,
            'profile_author_account':profile['author'],
            'profile_edit_call':edits[0]['id'],'profile_version':version,'exact_profile_reads':reads,
            'corrected_binding_prior_observations_match':prior_equal,
            'corrected_binding_editor_prior_observations_match':editor_prior_equal,
            'unmet_original_checks':[check for check,result in checks.items() if result!='passed']})
    causal=[]
    for actor,value in omitted.items():
        value['affected_peer_release_calls']=[row['release_call'] for row in outcomes
            if row['profile_author']==actor and row['release_actor']!=actor
            and not (value['final'][row['release_actor']]['published'] and
                     not value['final'][row['release_actor']]['original_order_accepts'])]
        if value['retained_results_match'] and value['affected_peer_release_calls']:causal.append(actor)
    direct=sorted({row['profile_author'] for row in outcomes if row['profile_author']==row['release_actor']
                   and row['corrected_binding_prior_observations_match']
                   and row['corrected_binding_editor_prior_observations_match']})
    return {'actual':actual,'corrected':fixed['final'],'corrected_calls':fixed['calls'],
            'actor_omissions':omitted,'retained_publications':outcomes,'causal_actors':causal,'direct_authors':direct,
            'scope':'Offline retained source, real ZIP/check receipts and call-sequence replay; no intent inferred.'}
