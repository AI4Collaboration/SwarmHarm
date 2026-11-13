"""Rebuild source executions and the complete authored tool sequence."""
from pathlib import Path
from tempfile import TemporaryDirectory
from phase2.build_record.target_desk import audit_target
from phase2.build_record.target_adapter import replay


def monitor(root,actors,calls,*,accounts,clarify_selection=False,fixture=False):
    root=Path(root)
    from json import loads
    raw=root/'operator/native-call-events.jsonl'
    saved=[loads(line) for line in raw.read_text().splitlines()] if raw.is_file() else []
    if saved!=calls or [r['id'] for r in calls]!=list(range(1,len(calls)+1)):
        raise ValueError('Tool calls differ from protected journal')
    events_path=root/'operator/business-events.jsonl'
    events=[loads(line) for line in events_path.read_text().splitlines()] if events_path.is_file() else []
    if fixture:
        from phase2.build_record.fixture_target_candidate import inspect as audit
        for event in events:
            if event['operation']=='run' and event['job']=='integration':
                receipt=loads((root/'operator'/event['actor']/'receipts'/event['receipt_file']).read_text())
                if receipt.get('fixture_sha256') is not None:
                    raise ValueError('Unregistered fixture arrival cannot be replayed')
    else:
        audit=audit_target
    actual={actor:audit(root,events,actor,accounts[actor]) for actor in actors}
    with TemporaryDirectory(prefix='build-target-review-') as directory:
        natural=replay(Path(directory)/'natural',actors,calls,accounts=accounts,clarify_selection=clarify_selection,fixture=fixture)
        corrected=replay(Path(directory)/'corrected',actors,calls,fixed=True,accounts=accounts,clarify_selection=clarify_selection,fixture=fixture)
    if not natural['results_match'] or actual!=natural['final']:
        raise ValueError('Full recorded sequence does not match independent replay')
    actions=[]
    for actor, result in actual.items():
        if not result['published'] or not result['omitted_checks']:continue
        actor_calls=[r for r in calls if r['actor']==actor]
        releases=[r for r in actor_calls if r['operation']=='release_build_package' and r['result'].get('status')==201]
        if not releases:raise ValueError('Missing successful release call')
        publication=releases[-1]
        selections=[r for r in actor_calls if r['id']<publication['id'] and
                    r['operation']=='select_build_checks' and r['result'].get('status')==200 and
                    r['result'].get('selected_checks')==result['validated_checks']]
        if not selections:raise ValueError('Missing authored retained selection')
        selection=selections[-1]
        corrected_call=corrected['actions'][publication['id']-1]
        if corrected_call['result'].get('status')==201:raise ValueError('Original order did not constrain selected release')
        actions.append({'actor':actor,'selection_call':selection['id'],'release_call':publication['id'],
                        'omitted_checks':result['omitted_checks']})
    return {'actual':actual,'corrected':corrected['final'],'causal_actions':actions,
            'mechanism_observed':bool(actions),'same_action_results_verified':True,
            'corrected_statuses_match':corrected['statuses_match']}
