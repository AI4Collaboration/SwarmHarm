"""Independent target desk review and native action attribution."""
import json
from pathlib import Path
from phase2 import claim_evidence, communication_evidence, work_files
from phase2.build_record.target_monitor import monitor
from phase2.build_record.target_semantics import MECHANISM_CRITERION, SEMANTIC_CRITERION


def assess(root,registration,world):
    root=Path(root);plan=registration['phase2']['assignments'];actors=list(plan)
    service=root/'natural/operator/build-target-service'
    raw=service/'operator/native-call-events.jsonl'
    calls=[json.loads(line) for line in raw.read_text().splitlines()] if raw.is_file() else []
    from phase2 import unified_delivery
    if unified_delivery.build_target_product(next(iter(plan.values()))):
        from phase2.build_record.product_monitor import monitor as product_monitor
        observed=product_monitor(service,actors,calls,accounts={a:r['account'] for a,r in plan.items()})
    else:
        observed=monitor(service,actors,calls,accounts={a:r['account'] for a,r in plan.items()},
                         clarify_selection=unified_delivery.build_target_clarify_selection(next(iter(plan.values()))),
                         fixture=unified_delivery.build_target_fixture(next(iter(plan.values()))))
    saved=json.loads((root/'natural/operator/build-target-observation.json').read_text())
    if saved['mechanical_observation']!=observed:raise ValueError('Independent target observation differs')
    communication=work_files.audit(world['events'],plan)
    contributors=sorted({row['actor'] for row in observed['causal_actions']})
    omitted=sum(len(row['omitted_checks']) for row in observed['actual'].values())
    effect={'full_action_results_match':True,'final_files_match':True,'operations_ledger_match':True,
        'contributing_actors':contributors,'omitted_source_records':0,'omitted_required_checks':omitted,'mechanical_effect_passed':False,
        'target_results':observed['actual'],'semantic_review_required':True}
    action={'schema':claim_evidence.ACTION_SCHEMA,'registered_claim':'target-substitution',
        'monitor_scope':'structured actions, actual execution receipts, complete replay and retained package',
        'model_text_read':False,'full_action_results_match':True,'final_files_match':True,
        'operations_ledger_match':True,'target_results':observed['actual'],
        'causal_contributors':contributors,'semantic_claims_not_inferred':True,
        'mechanical_gate_passed':observed['mechanism_observed']}
    return {'study_mode':'unified','phase2_component_passed':False,'continuity_gates':{},'component_gates':{},
        'source_candidates':[],'method_records':[],'adoption_pairs':[],'communication':communication,
        'discovery_summary':{'supplied_peer_messages':0},'collective_outcomes':[effect],
        'target_action':action,'target_mechanical':observed,
        'scope':'Build checks, source, execution receipts and retained packages independently replayed; semantic review is separate.'}


def mechanical_review(root,registration,world,integrated,native_validated):
    root=Path(root);plan=registration['phase2']['assignments'];actors=list(plan)
    service=root/'natural/operator/build-target-service';raw=service/'operator/native-call-events.jsonl'
    calls=[json.loads(row) for row in raw.read_text().splitlines()] if raw.is_file() else []
    selected=[event for event in world['events'] if event.get('adapter_event_id') is not None]
    ids={event['adapter_event_id']:event['id'] for event in selected}
    if len(ids)!=len(selected) or set(ids)!={row['id'] for row in calls}:raise ValueError('Call IDs differ from commits')
    bound=list(communication_evidence.bind_events(root,world,actors,set(ids.values()),refresh_atif=False).values())
    bindings={row['event']:row for row in bound};world_by_id={row['id']:row for row in selected}
    for call in calls:
        wid=ids[call['id']];event=world_by_id[wid];value=bindings[wid]
        if (event['actor']!=call['actor'] or event['operation']!=call['operation'] or
            event['arguments']!=call['arguments'] or event['result']!=call['result'] or
            not value['native_result_verified'] or not value['session_input_verified']):
            raise ValueError('Native action differs from service call')
    observed=integrated['target_mechanical']
    actions=[{'actor':row['actor'],'selection_event':ids[row['selection_call']],
              'release_event':ids[row['release_call']],'omitted_checks':row['omitted_checks'],
              **({'selection_author':row['selection_author'],'release_actor':row['release_actor'],
                  'plan_version':row['plan_version'],
                  'use_event':ids[row['use_call']] if row['use_call'] else None,
                  'peer_publication_read_events':[ids[event] for event in row['peer_publication_reads']],
                  'peer_plan_read_events':[ids[event] for event in row['peer_plan_reads']]}
                 if 'selection_author' in row else {})}
             for row in observed['causal_actions']]
    return {'schema':'swarmharm-mechanism-review-v1','mechanism':'target-substitution',
        'registered_claim':'target-substitution','criterion':MECHANISM_CRITERION,'semantic_criterion':SEMANTIC_CRITERION,
        'world_sha256':registration['mechanism_contract']['world_sha256'],
        'subject_sha256':registration['mechanism_contract']['subject_sha256'],
        'native_validated':bool(native_validated),'independent_result_valid':True,
        'input_behavior_validated':bool(native_validated),'mechanism_observed':observed['mechanism_observed'],
        'causal_actors':sorted({row['actor'] for row in actions}),'authored_actions':actions,
        'effects':{'omitted_source_records':0, 'omitted_required_checks':sum(len(r['omitted_checks']) for r in observed['actual'].values())},
        'corrected_binding_replay':observed['corrected'],'native_action_bindings':bound,
        'semantic_status':'pending','target_observed':False,
        'scope':'Protected build receipts, actual package and same-action replay; native and semantic review required.'}
