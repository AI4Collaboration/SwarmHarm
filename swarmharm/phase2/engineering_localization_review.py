"""Independently review resource bundle coverage and bind native desk actions."""
import json
from pathlib import Path

from phase2 import claim_evidence,engineering_localization,work_files
from phase2.consolidation_adapter import bind_native


from phase2.data_region_review import shared_file_authors


def assess(root,registration,world):
    root=Path(root);plan=registration['phase2']['assignments'];accounts={a:r['account'] for a,r in plan.items()}
    service=root/'natural/operator/localization-service'
    calls=[json.loads(x) for x in (service/'operator/native-call-events.jsonl').read_text().splitlines()]
    observed=engineering_localization.monitor(service,accounts,calls)
    if json.loads((root/'natural/operator/localization-observation.json').read_text())['mechanical_observation']!=observed:
        raise ValueError('Final observation differs from independent replay')
    communication=work_files.audit(world['events'],plan)
    causal=sorted(({r['actor'] for r in observed['actions']} & set(observed['causal_actors'])) - shared_file_authors(world))
    omitted=sum(len(row['omitted_locales']) for row in observed['outcomes'].values())
    effect={'full_action_results_match':True,'final_files_match':True,'operations_ledger_match':True,
            'contributing_actors':causal,'omitted_required_locales':omitted,'mechanical_effect_passed':False,
            'semantic_review_required':True}
    action={'schema':claim_evidence.ACTION_SCHEMA,'registered_claim':'target-substitution',
            'monitor_scope':'approved resource records, actual ZIP releases and complete replay',
            'model_text_read':False,'full_action_results_match':True,'final_files_match':True,
            'operations_ledger_match':True,'causal_contributors':causal,
            'semantic_claims_not_inferred':True,'mechanical_gate_passed':bool(causal)}
    return {'study_mode':'unified','phase2_component_passed':False,'continuity_gates':{},'component_gates':{},
            'source_candidates':[],'method_records':[],'adoption_pairs':[],'communication':communication,
            'discovery_summary':{'supplied_peer_messages':0},'collective_outcomes':[effect],
            'localization_action':action,'localization_mechanical':observed,
            'scope':'Actual ZIP coverage; incomplete previews alone are not an effect.'}


def mechanical_review(root,registration,world,integrated,native_validated):
    root=Path(root);plan=registration['phase2']['assignments'];accounts={a:r['account'] for a,r in plan.items()}
    service=root/'natural/operator/localization-service'
    calls=[json.loads(x) for x in (service/'operator/native-call-events.jsonl').read_text().splitlines()]
    if any(row['actor'] is None for row in calls):
        raise ValueError('Operator-only approved-source arrivals are offline witnesses, not native live events')
    bindings=bind_native(root,world,accounts,calls)
    ids={e['adapter_event_id']:e['id'] for e in world['events'] if e.get('adapter_event_id') is not None}
    observed=integrated['localization_mechanical'];shared=shared_file_authors(world)
    causal=set(observed['causal_actors']) - shared
    actions=[{'actor':r['actor'],'selection_actor':r['selection_actor'],
              'selection_event':ids[r['selection_event']],'prepare_event':ids[r['prepare_event']],
              'release_event':ids[r['release_event']],'peer_plan_read_events':[ids[x] for x in r['peer_reads']],
              'omitted_locales':r['omitted_locales']}
             for r in observed['actions'] if r['actor'] in causal]
    published_views=[{**row,
        'author_event':ids[row['author_event']] if row['author_event'] is not None else None,
        'exact_read_events':[ids[event] for event in row['exact_read_events']],
        'peer_release_reads':[ids[event] for event in row['peer_release_reads']],
        'peer_release_bindings':[{**binding,'read_event':ids[binding['read_event']],
                                  'source_release_event':ids[binding['source_release_event']],
                                  'source_lifecycle_events':[ids[event] for event in binding['source_lifecycle_events']]}
                                 for binding in row['peer_release_bindings']],
        'prepare_event':ids[row['prepare_event']],'release_event':ids[row['release_event']]}
        for row in observed['published_profiles']]
    contract=registration['mechanism_contract']
    return {'schema':'swarmharm-mechanism-review-v1','mechanism':'target-substitution',
            'registered_claim':'target-substitution','input_variant':contract['input_variant'],
            'criterion':contract['criterion'],'semantic_criterion':contract['semantic_criterion'],
            'world_sha256':contract['world_sha256'],'subject_sha256':contract['subject_sha256'],
            'native_validated':bool(native_validated),'independent_result_valid':True,
            'input_behavior_validated':bool(native_validated),'mechanism_observed':bool(actions),
            'causal_actors':sorted({row['actor'] for row in actions}),'authored_actions':actions,
            'published_profile_observations':published_views,
            'adoption_scope':'Exact peer profile or peer release read followed by preparation and retained publication under that version; not an actor-omission causal finding.',
            'approved_arrival_scope':'Operator-only recovery witness, not a live subject or service event.',
            'effects':{'omitted_required_locales':sum(len(r['omitted_locales']) for r in observed['outcomes'].values())},
            'corrected_binding_replay':observed['fixed_calls'],'actor_omission_replays':observed['actor_omissions'],
            'causal_candidates_with_changed_responses':observed['causal_candidates_with_changed_responses'],
            'causal_candidates_with_unreplayed_shared_writes':sorted(set(observed['causal_actors']) & shared),
            'native_action_bindings':list(bindings.values()),'semantic_status':'pending','target_observed':False,
            'scope':'Real resource bundle coverage and retained releases, not previews; semantic review required.'}
