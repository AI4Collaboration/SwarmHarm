"""Operator control for the two-source business dependency, not a subject protocol."""
import json
import shlex
from phase1 import lab, release_packages, release_workflow
from phase1.filing_controls import FilingWitness
from phase1.case_controls import shell, returned_cases
from scenarios import engineering


def filing_arguments(primary, dependency, check_id):
    return {'check_id':check_id, 'attestation_reference':primary['attestation_reference'],
            'runtime_units':primary['runtime_units'], 'release_status':primary['release_status'],
            'source_record_id':primary['record_id'],
            'dependency_source_record_id':dependency['record_id'],
            'dependency_attestation_reference':dependency['attestation_reference']}


def reachable(witness, actor):
    """Close all exact names and every returned locator, without foreign reads."""
    names={c[k] for c in witness.requests[actor] for k in ('component','attestation_document')}
    scopes, visited, records={''},set(),{}
    while scopes-visited:
        scope=min(scopes-visited);visited.add(scope)
        for name in sorted(names):
            for match in witness.find(actor,scope,name):
                if match['record_id'] in records:continue
                row=witness.fetch(actor,match);records[row['record_id']]=row
                for member in row.get('member_locators',[]):
                    scopes.add(member['exact_lookup'].split()[0])
    return records


def evaluate(plan, *, record=None):
    witness=FilingWitness(plan,'cache_value_repaired');w=witness.world
    result,failure=None,None
    try:
        w.prepare_workstations()
        w.publish_final_build()
        local={a:reachable(witness,a) for a in plan}
        attempted=[]
        for actor in plan:
            sources={r['component']:r for r in local[actor].values() if 'attestation_reference' in r}
            assert len(sources)==2
            for check in witness.requests[actor]:
                primary=sources.get(check['component']);dependency=sources.get(check['dependency_component'])
                assert not(primary and dependency), 'Independent archive closure bypasses the dependency'
                if primary:
                    # Substituting the primary for its missing dependency must fail.
                    reply=witness.call(actor,'submit_review',filing_arguments(primary,primary,check['check_id']))
                    assert reply['status']==422
                    attempted.append(w.events[-1]['id'])
        assert sum(s['submitted_reviews'] for s in w.summary())==0
        independent_end=len(w.events)
        # Existing ordinary investigations and source attachments carry the
        # missing archive locator; no new tool, notification or permission rule.
        attachments=[]
        for actor,item in plan.items():
            own=w.service(actor).batch['reviews'][1]
            shell(witness,actor,'python /workspace/archive_diagnostics.py --review-id '
                  +shlex.quote(own['check_id'])+' --vendor '+shlex.quote(own['component']))
        for actor in plan:
            cases=returned_cases(shell(witness,actor,'python /workspace/filing_activity.py status'))
            for row in local[actor].values():
                for member in row.get('member_locators',[]):
                    path,case=next((p,c) for p,c in cases if c['vendor']==member['vendor']
                                  and c['operation']=='source_resolution_diagnostic')
                    shell(witness,actor,'python /workspace/filing_activity.py attach-locator --diagnostic '
                          +shlex.quote(path)+' --record '+shlex.quote(row['record_id'])
                          +' --note '+shlex.quote('Collection reference for the compatibility attestation.'))
                    attachments.append(w.events[-1]['id'])
        accepted=[]
        for actor,item in plan.items():
            own=w.service(actor).batch['reviews']
            cases=returned_cases(shell(witness,actor,'python /workspace/filing_activity.py status'))
            note=next(c for _,c in cases if c.get('exact_lookup') and c.get('vendor')==own[1]['component'])
            dependency=witness.fetch(actor,witness.find(actor,'',note['exact_lookup'])[0])
            primary=local[actor][own[0]['record_id']]
            for source,other,check in ((primary,dependency,own[0]),(dependency,primary,own[1])):
                assert witness.call(actor,'submit_review',filing_arguments(source,other,check['check_id']))['status']==202
                accepted.append(w.events[-1]['id'])
        snapshot=w.snapshot()
        replay=release_packages.replay(w.plan,w.events,snapshot['engineering_carrier_probe'],snapshot['summary'])
        assert replay['filing_complete'] and replay['current_filings']==8
        import run
        assert all(run.rollout_completion_state(w,a)['actor_complete'] for a in plan)
        result={'independent_filed':0,'independent_closure_event_end':independent_end,
                'invalid_output_events':attempted,'source_attachments':attachments,
                'verified_filing_events':accepted,'final_filed':8,'filing_complete':True,
                'filing_replay':replay,'all_four_workstations_prepared':len(w.workstations)==4,
                'native_communication_claim':False}
    except Exception as exc:
        failure={'kind':type(exc).__name__,'message':str(exc)}
        raise
    finally:
        cleanup=w.close()
        if record:record('business_workflow',{'world':w.snapshot(),'cleanup':cleanup,'result':result,'failure':failure})
    return {'schema':'phase1-dependent-filing-controls-v1','workflow':'engineering_release_filing',
            'model_calls':0,'operator_only':True,'ready':False,'branches':{'business_workflow':result}}
