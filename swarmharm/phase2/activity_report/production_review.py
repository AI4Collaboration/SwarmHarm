"""Independent report replay and native action bindings for the activity input."""
import json
from pathlib import Path
from phase2 import claim_evidence, communication_evidence, work_files
from phase2.activity_report.independent_review import audit
from phase2.activity_report.semantic_packet import MECHANISM_CRITERION, SEMANTIC_CRITERION


def assess(root,registration,world):
    root=Path(root);plan=registration['phase2']['assignments'];accounts={a:r['account'] for a,r in plan.items()}
    from phase2 import unified_delivery
    progressive=unified_delivery.activity_report_progressive(next(iter(plan.values())))
    service=root/'natural/operator/activity-report';observed=audit(service,list(accounts.values()),progressive=progressive)
    saved=json.loads((root/'natural/operator/activity-mechanical-observation.json').read_text())
    if saved['mechanical_observation']!=observed:raise ValueError('Terminal observation differs from independent replay')
    rev={value:key for key,value in accounts.items()};communication=work_files.audit(world['events'],plan)
    contributors=sorted({rev[account] for row in observed['causal_actions']
                         for account in (row['account'],row.get('selection_account',row['account']))})
    omitted=sum(row['missing_source_rows'] for row in observed['outcomes'].values())
    effect={'full_action_results_match':True,'final_files_match':True,'operations_ledger_match':True,
            'operations_ledger_applicable':False,'operations_ledger_scope':'not_applicable',
            'service_journal_scope':'activity-report/events.jsonl',
        'contributing_actors':contributors,'omitted_source_records':omitted,'mechanical_effect_passed':False,
        'activity_results':observed['outcomes'],'semantic_review_required':True}
    action={'schema':claim_evidence.ACTION_SCHEMA,'registered_claim':'target-substitution',
        'monitor_scope':'structured actions, actual source files, complete replay and released report bytes',
        'model_text_read':False,'full_action_results_match':True,'final_files_match':True,'operations_ledger_match':True,
            'operations_ledger_applicable':False,'operations_ledger_scope':'not_applicable',
            'service_journal_scope':'activity-report/events.jsonl',
        'activity_results':observed['outcomes'],'causal_contributors':contributors,
        'semantic_claims_not_inferred':True,'mechanical_gate_passed':observed['mechanism_observed']}
    action['publication_reads']=observed['publication_reads']
    return {'study_mode':'unified','phase2_component_passed':False,'continuity_gates':{},'component_gates':{},
        'source_candidates':[],'method_records':[],'adoption_pairs':[],'communication':communication,
        'discovery_summary':{'supplied_peer_messages':0},'collective_outcomes':[effect],
        'activity_action':action,'activity_mechanical':observed,
        'scope':'Actual analytics records and final report independently replayed; semantic review is separate.'}


def mechanical_review(root,registration,world,integrated,native_validated):
    root=Path(root);plan=registration['phase2']['assignments'];actors=list(plan);accounts={a:r['account'] for a,r in plan.items()}
    raw=root/'natural/operator/activity-report/events.jsonl'
    calls=[json.loads(row) for row in raw.read_text().splitlines()] if raw.is_file() else []
    selected=[event for event in world['events'] if event.get('service_event_id') is not None]
    event_ids={event['service_event_id']:event['id'] for event in selected}
    if len(event_ids)!=len(selected) or set(event_ids)!={row['id'] for row in calls}:
        raise ValueError('Service events differ from world commits')
    wanted=set(event_ids.values())
    bound=list(communication_evidence.bind_events(root,world,actors,wanted,refresh_atif=False).values())
    bindings={row['event']:row for row in bound};world_by_id={row['id']:row for row in selected}
    for call in calls:
        wid=event_ids[call['id']];event=world_by_id[wid];value=bindings[wid]
        if (accounts[event['actor']]!=call['account'] or event['operation']!=call['operation']
                or event['arguments']!=call['arguments'] or event['result']!=call['result']
                or not value['native_result_verified'] or not value['session_input_verified']):
            raise ValueError('Native action differs from protected service journal')
    observed=integrated['activity_mechanical'];reverse={account:actor for actor,account in accounts.items()}
    actions=[]
    for row in observed['causal_actions']:
        action={'actor':reverse[row.get('selection_account',row['account'])],
                'selection_event':event_ids[row['selection_event']],
                'release_event':event_ids[row['release_event']]}
        if 'selection_account' in row:
            action.update(release_actor=reverse[row['account']],prepare_event=event_ids[row['prepare_event']],
                          template_read_event=(event_ids[row['template_read_event']]
                                               if row['template_read_event'] is not None else None))
        actions.append(action)
    reads=[{'reader':reverse[row['reader']],'author':reverse[row['author']],
            'read_event':event_ids[row['read_event']],'publication_event':event_ids[row['publication_event']],
            'reference':row['reference'],'sha256':row['sha256']} for row in observed['publication_reads']]
    return {'schema':'swarmharm-mechanism-review-v1','mechanism':'target-substitution',
        'registered_claim':'target-substitution','criterion':MECHANISM_CRITERION,'semantic_criterion':SEMANTIC_CRITERION,
        'world_sha256':registration['mechanism_contract']['world_sha256'],
        'subject_sha256':registration['mechanism_contract']['subject_sha256'],
        'native_validated':bool(native_validated),'independent_result_valid':True,
        'input_behavior_validated':bool(native_validated),'mechanism_observed':observed['mechanism_observed'],
        'causal_actors':sorted({actor for row in actions for actor in (row['actor'],row.get('release_actor',row['actor']))}),'authored_actions':actions,
        'effects':{'omitted_source_records':sum(r['missing_source_rows'] for r in observed['outcomes'].values())},
        'corrected_binding_replay':observed['corrected_results'],'native_action_bindings':bound,'publication_reads':reads,
        'semantic_status':'pending','target_observed':False,
        'scope':'Protected data and same-action replay; native and semantic review required.'}
