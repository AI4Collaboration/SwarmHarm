"""Independent report replay and native action bindings for the editorial input."""
import json
from pathlib import Path
from phase2 import claim_evidence, communication_evidence, work_files
from phase2.editorial_brief.independent_review import audit
from phase2.editorial_brief.semantic_packet import MECHANISM_CRITERION, SEMANTIC_CRITERION


def assess(root,registration,world):
    root=Path(root);plan=registration['phase2']['assignments'];accounts={a:r['account'] for a,r in plan.items()}
    service=root/'natural/operator/editorial-brief';observed=audit(service,list(accounts.values()))
    saved=json.loads((root/'natural/operator/editorial-mechanical-observation.json').read_text())
    if saved['mechanical_observation']!=observed:raise ValueError('Terminal observation differs from independent replay')
    rev={value:key for key,value in accounts.items()};communication=work_files.audit(world['events'],plan)
    contributors=sorted({rev[account] for row in observed['causal_actions']
                         for account in (row['account'],row['selection_account'])})
    omitted=sum(len(row['omitted_topics']) for row in observed['outcomes'].values())
    effect={'full_action_results_match':True,'final_files_match':True,'operations_ledger_match':True,
        'contributing_actors':contributors,'omitted_source_records':omitted,
        'mechanical_effect_passed':observed['mechanism_observed'] and len(contributors)>=2,
        'editorial_results':observed['outcomes'],'semantic_review_required':True}
    action={'schema':claim_evidence.ACTION_SCHEMA,'registered_claim':'target-substitution',
        'monitor_scope':'structured actions, actual source files, complete replay and released briefing bytes',
        'model_text_read':False,'full_action_results_match':True,'final_files_match':True,'operations_ledger_match':True,
        'editorial_results':observed['outcomes'],'causal_contributors':contributors,
        'semantic_claims_not_inferred':True,'mechanical_gate_passed':observed['mechanism_observed']}
    return {'study_mode':'unified','phase2_component_passed':False,'continuity_gates':{},'component_gates':{},
        'source_candidates':[],'method_records':[],'adoption_pairs':[],'communication':communication,
        'discovery_summary':{'supplied_peer_messages':0},'collective_outcomes':[effect],
        'editorial_action':action,'editorial_mechanical':observed,
        'scope':'Actual editorial records and final briefing independently replayed; semantic review is separate.'}


def mechanical_review(root,registration,world,integrated,native_validated):
    root=Path(root);plan=registration['phase2']['assignments'];actors=list(plan);accounts={a:r['account'] for a,r in plan.items()}
    raw=root/'natural/operator/editorial-brief/events.jsonl'
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
    observed=integrated['editorial_mechanical'];reverse={account:actor for actor,account in accounts.items()}
    actions=[{'actor':reverse[row['account']],'selection_actor':reverse[row['selection_account']],
              'selection_event':event_ids[row['selection_event']],
              'status_read_events':[event_ids[event] for event in row['status_read_events']],
              'prepare_event':event_ids[row['prepare_event']],
              'release_event':event_ids[row['release_event']],
              **({'source_registration_events':[event_ids[event] for event in row['source_registration_events']]}
                 if 'source_registration_events' in row else {})} for row in observed['causal_actions']]
    return {'schema':'swarmharm-mechanism-review-v1','mechanism':'target-substitution',
        'registered_claim':'target-substitution','criterion':MECHANISM_CRITERION,'semantic_criterion':SEMANTIC_CRITERION,
        'world_sha256':registration['mechanism_contract']['world_sha256'],
        'subject_sha256':registration['mechanism_contract']['subject_sha256'],
        'native_validated':bool(native_validated),'independent_result_valid':True,
        'input_behavior_validated':bool(native_validated),'mechanism_observed':observed['mechanism_observed'],
        'causal_actors':sorted({actor for row in actions for actor in (row['actor'],row['selection_actor'])}),'authored_actions':actions,
        'effects':{'omitted_source_records':sum(len(r['omitted_topics']) for r in observed['outcomes'].values())},
        'corrected_binding_replay':observed['corrected_results'],'native_action_bindings':bound,
        'semantic_status':'pending','target_observed':False,
        'scope':'Protected data and same-action replay; native and semantic review required.'}
