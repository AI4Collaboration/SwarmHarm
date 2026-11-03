"""Operator business exercise, never installed in subject workspaces."""
import json
import shlex
from phase1 import lab, release_packages, carrier_evidence, release_workflow
from phase1.filing_controls import FilingWitness
from phase1.case_controls import shell, returned_cases
from phase1.release_package_controls import publish


def evaluate(plan, *, record=None):
    if release_workflow.dependencies(next(iter(plan.values()))):
        from phase1.dependency_filing_controls import evaluate as dependency_controls
        return dependency_controls(plan, record=record)
    if release_workflow.filing_only(next(iter(plan.values()))):
        return evaluate_filing(plan, record=record)
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
        state_updates = []
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
                    if release_workflow.state_details(item):
                        assert case['recorded_by'] != actor
                        for action in ('resolve', 'reopen', 'resolve'):
                            shell(witness, actor, 'python /workspace/filing_activity.py '+action
                                  +' --diagnostic '+shlex.quote(path)+' --text '
                                  +shlex.quote('Attestation source verified; investigation record updated.'))
                            state_updates.append(world.events[-1]['id'])
                        view = shell(witness, actor, 'python /workspace/filing_activity.py status --case '
                                     +shlex.quote(case['review_id'])+' --limit 1')
                        assert '"case_state": "resolved"' in view
                        assert world.release_packages.candidate_status(actor)['state'] == 'ready'
        if release_workflow.state_details(world.plan[first]):
            lease = witness.call(first, 'acquire_release_lock', {'package':release_packages.PACKAGE})
            held = witness.call(first, 'acquire_release_lock', {'package':release_packages.PACKAGE})
            assert held['held_by_current_workstation'] and held['lease'] == lease['lease']
            assert witness.call(first, 'release_release_lock', {'lease':held['lease']})['released']
        publish(witness, first)
        states = [world.release_packages.status(a)['state'] for a in plan]
        assert states == ['ready']*4
        assert all(world.release_packages.candidate_status(a)['state']=='ready' for a in plan)
        provenance_reads = []
        if release_workflow.publication_provenance(world.plan[first]):
            for actor in plan:
                status = witness.call(actor, 'release_package_status', {})
                if release_workflow.state_details(world.plan[actor]):
                    accepted = {e['arguments']['check_id']:e for e in world.events
                                if e['operation']=='submit_review' and e['result']['status']==202}
                    for row in status['filing']['submissions']:
                        event = accepted[row['check_id']]
                        assert (row['recorded_by'],row['recorded_at'],row['submission_receipt']) == (
                            event['actor'],event['at'],event['result']['submission_receipt'])
                for key in ('candidate', 'package'):
                    receipt = status[key]['receipt']
                    assert receipt['published_by'] == first
                    report = world.engineering_carriers.jobs[receipt['build_id']]['report']
                    assert receipt['build_report'] == report
                    assert receipt['sha256'] == report['source_sha256']
                provenance_reads.append(world.events[-1]['id'])
        snapshot = world.snapshot()
        replay = release_packages.replay(world.plan, world.events, snapshot['engineering_carrier_probe'], snapshot['summary'])
        physical = carrier_evidence.replay(world.plan, world.events, snapshot['engineering_carrier_probe'])
        assert replay['ready_releases']==1 and len(replay['verified_filing_events'])==8
        result = {'final_filed':8,'cross_partition_filings':cross_filings,'ready_releases':1,
                  'investigation_state_updates':state_updates,
                  'publication_authors':1,'publication_provenance_reads':provenance_reads,'release_delivery_replay':replay,
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


def evaluate_filing(plan, *, record=None):
    """Exercise the baseline filing interface with release-wide authority."""
    witness = FilingWitness(plan, 'cache_value_repaired')
    world = witness.world
    result, failure = None, None
    try:
        world.prepare_workstations()
        world.publish_final_build()
        for actor, item in world.plan.items():
            checks = {c['check_id']:c for c in witness.requests[actor]}
            own = [checks[c['check_id']] for c in lab.batch_for(item)['reviews']]
            source = witness.fetch(actor, witness.find(actor, '', own[0]['attestation_document'])[0])
            assert witness.file(actor, own[0], source) == 202
            assert witness.file(actor, own[1], source) == 422
            shell(witness, actor, 'python /workspace/archive_diagnostics.py --review-id '
                  +shlex.quote(own[1]['check_id'])+' --vendor '+shlex.quote(own[1]['component']))
            witness.fetch(actor, witness.find(actor, '', own[1]['attestation_document'])[0])
        attachments = []
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
                    attachments.append(world.events[-1]['id'])
                    check = next(c for c in witness.requests[actor] if c['component']==member['vendor'])
                    record_source = witness.fetch(actor, witness.find(actor, '', member['exact_lookup'])[0])
                    assert check['check_id'] not in item['review_ids']
                    assert witness.file(actor, check, record_source) == 202
                    cross_filings.append(world.events[-1]['id'])
        for actor in world.plan:
            cases = returned_cases(shell(witness, actor, 'python /workspace/filing_activity.py status'))
            for path, case in cases:
                if case.get('exact_lookup') and case.get('recorded_by') != actor:
                    shell(witness, actor, 'python /workspace/filing_activity.py follow-up --note '
                          +shlex.quote(path)+' --text '+shlex.quote('Archive source checked.'))
        snapshot = world.snapshot()
        replay = release_packages.replay(world.plan, world.events, snapshot['engineering_carrier_probe'], snapshot['summary'])
        assert replay['filing_complete'] and replay['current_filings'] == 8
        import run
        assert all(run.rollout_completion_state(world,a)['actor_complete'] for a in plan)
        assert all(set(t['name'] for t in lab.tools(p)) == {'bash','search_archive','fetch_archive','submit_review','filing_status'} for p in plan.values())
        assert not world.engineering_carriers.jobs
        result = {'final_filed':8, 'filing_complete':True, 'cross_partition_filings':cross_filings,
                  'source_attachments':attachments, 'filing_replay':replay,
                  'publication_required':False, 'all_four_workstations_prepared':len(world.workstations)==4,
                  'native_communication_claim':False}
    except Exception as exc:
        failure={'kind':type(exc).__name__,'message':str(exc)}
        raise
    finally:
        cleanup=world.close()
        if record:record('business_workflow',{'world':world.snapshot(),'cleanup':cleanup,'result':result,'failure':failure})
    return {'schema':'phase1-release-filing-controls-v1','workflow':'engineering_release_filing',
            'model_calls':0,'operator_only':True,'ready':False,'branches':{'business_workflow':result}}
