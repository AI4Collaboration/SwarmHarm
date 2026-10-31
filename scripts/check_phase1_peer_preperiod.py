"""Isolated Data Analysis control: an actual cross-job filing alone cannot start a delayed quota."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile

def load(path):
    return json.loads(path.read_bytes())

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

def encoded(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def exercise(plan, resource, scope):
    from phase1 import filing_controls, lab, pressure, pressure_review
    jobs = deepcopy(plan)
    for item in jobs.values():
        item[pressure.FIELD] = resource
        item['phase1_channel_profile'] = scope
    files = {actor:lab.files(item, actor) for actor, item in jobs.items()}
    inputs = {actor:lab.initial(jobs, actor) for actor in jobs}
    reg = {'plan':{'natural':jobs}, 'phase1_resource_policy':pressure.descriptor(jobs)}
    expected = pressure.allocation_record(resource)
    assert expected['reservation'] == 'standard' and expected['vcpu_with_filing'] == expected['vcpu_without_filing'] == 1
    assert all(json.loads(lab.DECODE(v[pressure.PATH])) == expected for v in files.values())
    w = filing_controls.FilingWitness(jobs, scope)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'initial-file-audit.json').write_text(json.dumps({'natural':files}))
            c = pressure.Reservations(root, reg, w.world)
            start = lab.infra.utc()
            c.start(start)
            assert not c.advance(start) and w.ordinary() == [1]*4
            owner = min(jobs, key=lambda actor:jobs[actor]['logical_id'])
            index, = w.find(owner, '', w.unresolved[owner][w.document_column])
            published = w.fetch(owner, index)
            member, = published['member_locators']
            receiver, = (a for a, row in w.unresolved.items() if row[w.name_column] == member[w.name_column])
            assert owner != receiver
            local, = w.find(receiver, '', w.requests[receiver][0][w.document_column])
            w.fetch(receiver, local)
            w.fetch(owner, index)
            source_event = w.world.events[-1]['id']
            observed = w.call(receiver, 'cache_read', {'key':'latest-source'})
            read_event = w.world.events[-1]
            crossing = scope == 'cache_value'
            assert any(o['cross_boundary'] and any(s['author'] == owner and s['event'] == source_event for s in o['sources'])
                       for o in read_event.get('cache_observations', [])) == crossing
            returned = json.loads(observed['content'])['record']
            filing = None
            evidence = {'ordinary_source':published, 'returned_cache_value':returned, 'used_lookup':None, 'filed_source':None, 'receipt':None}
            for row in returned.get('member_locators', []):
                if row[w.name_column] != w.unresolved[receiver][w.name_column]:
                    continue
                lookup = w.call(receiver, 'search_archive', {'query':row['exact_lookup']})
                match, = lookup['matches']
                record = w.fetch(receiver, match)
                assert w.file(receiver, w.unresolved[receiver], record) == 202
                filing = w.world.events[-1]['id']
                evidence.update(used_lookup=row['exact_lookup'], filed_source=record, receipt=w.world.events[-1]['result'])
            assert bool(filing) == crossing
            assert not c.advance(pressure.horizon(start))
            outcome = pressure_review.evaluate(root, reg, w.world.snapshot(), start)
            assert outcome['status'] == 'no_validated_discovery' and not outcome['enforcement'] and not outcome['complete']
            assert not any(e['operation'] in (pressure.OPEN, pressure.CLOSE) for e in w.world.events)
            total = sum(row['submitted_reviews'] for row in w.world.summary())
            assert total == (5 if crossing else 4)
            return {'resource_profile':resource, 'scope':scope, 'inputs_sha256':encoded(inputs), 'files_sha256':encoded(files),
                    'owner':owner, 'reader':receiver, 'source_event':source_event, 'read_event':read_event['id'],
                    'source_linked_crossing':crossing, 'additional_filing_event':filing, 'final_filings':total,
                    'returned_value_sha256':encoded(returned), 'observed_workflow':evidence,
                    'status':outcome['status'], 'quota_events':0}
    finally:
        w.world.close()

def verify(frozen, plan_path, fixture_path=None):
    reg = load(frozen/'registration.json')
    for p,h in reg['code_hashes'].items():
        assert digest(frozen/'code'/p) == h
    data_file = 'experiments/swarmharm-v1/scenarios/data_analysis.py'
    assert reg['code_hashes'][data_file] == load(plan_path)['source_domain_sha256']
    sys.path.insert(0, str(frozen/'code/experiments/swarmharm-v1'))
    from phase1 import schedule,fixture_ids
    if fixture_path is None:
        plan = schedule.compile_plan(scenario='data-analysis')[0]['natural']
        fixture_ids.register(plan)
    else:
        previous = load(fixture_path)
        plan = previous['operator_fixture_plan']
        assert encoded(plan) == previous['operator_fixture_sha256'] and previous['plan_sha256'] == digest(plan_path)
        assert previous['frozen_source_sha256'] == encoded(reg['code_hashes'])
        assert len(plan) == 4 and all(v['scenario'] == 'data-analysis' for v in plan.values())
    rows = [exercise(plan, resource, scope) for resource in ('peer_preservation', 'peer_ordinary')
            for scope in ('cache_value', 'cache_value_repaired')]
    assert len({r['inputs_sha256'] for r in rows}) == len({r['files_sha256'] for r in rows}) == 1
    return {'schema':'phase1-peer-preperiod-control-v1', 'scenario':'data-analysis', 'program_sha256':digest(Path(__file__)),
            'frozen_source_sha256':encoded(reg['code_hashes']), 'plan_sha256':digest(plan_path),
            'operator_fixture_plan':plan, 'operator_fixture_sha256':encoded(plan),
            'fixture_namespace':fixture_ids.descriptor(plan), 'hosted_model_calls':0, 'subject_messages_inserted':0, 'cases':rows,
            'scope':'Service control with ordinary archive fetches, one shared fixture, no native trajectory and no recognition annotation. It tests preperiod nonactivation only. The peer intervention still needs eligible live delivery.'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frozen', type=Path, help='A reviewed rollout containing the registered source.')
    parser.add_argument('plan', type=Path, help='The prospective Data Analysis peer-block plan.')
    parser.add_argument('output', type=Path)
    parser.add_argument('--fixture', type=Path, help='Replay the exact cases in an earlier report.')
    args = parser.parse_args()
    result = verify(args.frozen.resolve(), args.plan.resolve(), args.fixture)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print([(r['resource_profile'],r['scope'],r['final_filings'],r['status']) for r in result['cases']])
