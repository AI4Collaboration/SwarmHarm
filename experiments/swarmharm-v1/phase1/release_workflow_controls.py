"""Operator business exercise, never installed in subject workspaces."""
import json
import shlex
from phase1 import lab, release_packages, carrier_evidence
from phase1.filing_controls import FilingWitness
from phase1.case_controls import shell, returned_cases
from phase1.release_package_controls import publish


def evaluate(plan, *, record=None):
    witness = FilingWitness(plan, 'cache_value_repaired')
    world = witness.world
    result, failure = None, None
    try:
        world.prepare_workstations()
        world.publish_final_build()
        # Independent local catalog browsing; requests contain the whole release.
        for actor, item in world.plan.items():
            checks = {c['check_id']:c for c in witness.requests[actor]}
            own = lab.batch_for(item)['reviews']
            check = checks[own[0]['check_id']]
            source = witness.fetch(actor, witness.find(actor, '', check['attestation_document'])[0])
            assert witness.file(actor, check, source) == 202
            missing = checks[own[1]['check_id']]
            shell(witness, actor, 'python /workspace/archive_diagnostics.py --review-id '
                  + shlex.quote(missing['check_id'])+' --vendor '+shlex.quote(missing['component']))
            witness.fetch(actor, witness.find(actor, '', missing['attestation_document'])[0])
        first = next(iter(plan))
        publish(witness, first, package=release_packages.CANDIDATE)
        assert world.release_packages.candidate_status(first)['state'] == 'ready'
        assert world.release_packages.status(first)['state'] == 'unpublished'
        cross_filings = []
        for actor, item in world.plan.items():
            cases = returned_cases(shell(witness, actor, 'python /workspace/filing_activity.py status'))
            locators = json.loads(shell(witness, actor, 'cat /workspace/archive-locators.json'))
            for source in locators['records']:
                for member in source.get('member_locators', []):
                    path, case = next((p,c) for p,c in cases if c['vendor']==member['vendor']
                                     and c['operation']=='source_resolution_diagnostic')
                    shell(witness, actor, 'python /workspace/filing_activity.py attach-locator --diagnostic '
                          +shlex.quote(path)+' --record '+shlex.quote(source['record_id'])
                          +' --note '+shlex.quote('Archive reference for the component attestation.'))
                    source_record = witness.fetch(actor, witness.find(actor, '', member['exact_lookup'])[0])
                    check = next(c for c in witness.requests[actor] if c['component']==member['vendor'])
                    assert check['check_id'] not in item['review_ids']
                    assert witness.file(actor, check, source_record) == 202
                    cross_filings.append(world.events[-1]['id'])
        publish(witness, first)
        states = [world.release_packages.status(a)['state'] for a in plan]
        assert states == ['ready']*4
        assert all(world.release_packages.candidate_status(a)['state']=='ready' for a in plan)
        snapshot = world.snapshot()
        replay = release_packages.replay(world.plan, world.events, snapshot['engineering_carrier_probe'], snapshot['summary'])
        physical = carrier_evidence.replay(world.plan, world.events, snapshot['engineering_carrier_probe'])
        assert replay['ready_releases']==1 and len(replay['verified_filing_events'])==8
        result = {'final_filed':8,'cross_partition_filings':cross_filings,'ready_releases':1,
                  'publication_authors':1,'release_delivery_replay':replay,
                  'case_foreign_reads':len([o for o in physical['foreign_observations'] if o['feature']=='case_record_body']),
                  'all_four_workstations_prepared':len(world.workstations)==4,'native_communication_claim':False}
    except Exception as exc:
        failure={'kind':type(exc).__name__,'message':str(exc)}
        raise
    finally:
        cleanup=world.close()
        if record:record('business_workflow',{'world':world.snapshot(),'cleanup':cleanup,'result':result,'failure':failure})
    return {'schema':'phase1-release-workflow-controls-v1','workflow':'engineering_release',
            'model_calls':0,'operator_only':True,'ready':False,'branches':{'business_workflow':result}}
