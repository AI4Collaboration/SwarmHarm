"""Verify that pressure attaches to a rollout independently of its task, channel and repair."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def inputs(plan, lab, pressure):
    output = {}
    for actor, assignment in plan.items():
        files = lab.files(assignment, actor).copy()
        record = files.pop(pressure.PATH, None)
        if record is not None:
            assert json.loads(lab.DECODE(record)) == pressure.allocation_record(assignment[pressure.FIELD])
        output[actor] = (lab.initial(plan, actor), files, lab.batch_for(assignment))
    return output


def probe(plan, service):
    cache = service.Cache(plan)
    source, reader = sorted(plan)[:2]
    results = []
    for i, (actor, op, args) in enumerate([
        (source, 'cache_store', {'key':'calculation','kind':'derived','content':'calculated value'}),
        (source, 'cache_order', {'order':['derived','source','receipt']}),
        (reader, 'cache_read', {'key':'calculation'}),
        (reader, 'cache_status', {})], 1):
        results.append(cache.call(actor, op, args, i))
    return results


def audit(source_root):
    reg = read(source_root/'registration.json')
    for rel, rhs in reg['code_hashes'].items():
        assert digest(source_root/'code'/rel) == rhs
    sys.path.insert(0, str(source_root/'code/experiments/swarmharm-v1'))
    from phase1 import cache_channels, channel_design, fixture_ids, lab, pressure, schedule, topology as visibility_graph
    grid = channel_design.proposal()['cells']
    profiles = [None, *pressure.ALLOCATIONS]
    assert len(grid) == len({c['cell_id'] for c in grid}) == 24
    cases = []
    for scenario in channel_design.DOMAINS:
        # Opaque handles may differ between rollouts. Hold them fixed within each compatibility comparison.
        ids = iter(['job-compat-1','job-compat-2','job-compat-3','job-compat-4'])
        initial = schedule.compile_plan(scenario=scenario, id_factory=ids.__next__)[0]['natural']
        fixture_ids.register(initial)
        for cell in (c for c in grid if c['scenario']==scenario):
            plan = deepcopy(initial)
            profile = cell['prepare_profile']
            for a in plan.values():
                a['phase1_channel_profile'] = profile
            comparison = inputs(plan, lab, pressure)
            baseline, topology = channel_design.compile_condition(profile, plan)
            no_plugin = probe(plan, cache_channels)
            descriptor = {k:v for k,v in baseline.items() if k!='pressure_condition'}
            choices = []
            for resource in profiles:
                mounted = deepcopy(plan)
                if resource is not None:
                    for a in mounted.values():
                        a[pressure.FIELD] = resource
                policy = pressure.descriptor(mounted)
                condition, visibility = channel_design.compile_condition(profile, mounted)
                assert visibility == topology and {k:v for k,v in condition.items() if k!='pressure_condition'} == descriptor
                assert inputs(mounted,lab,pressure) == comparison and probe(mounted,cache_channels) == no_plugin
                for actor,a in mounted.items():
                    assert (pressure.PATH in lab.files(a,actor)) == (resource is not None)
                effective = {'study_mode':'phase1','scenario':scenario,'cue_condition':'agent_initiated_activity','topology':visibility_graph.validate(visibility,mounted),
                             'plan':{'natural':mounted},'phase1_channel_condition':condition,'input_revision':fixture_ids.INPUT_REVISION,
                             'phase1_archive_identifiers':fixture_ids.descriptor(mounted)}
                if policy is not None:
                    assert policy['profile'] == resource
                    effective['phase1_resource_policy'] = policy
                assert channel_design.valid_registered_exposure(effective)
                choices.append(resource or 'detached')
            cases.append({'cell_id':cell['cell_id'],'pair_id':scenario+'__'+cell['carrier'],'attachments_checked':choices})
    return {'schema':'phase1-pressure-attachment-compatibility-v1','frozen_reference_sha256':digest(source_root/'registration.json'),
            'program_sha256':digest(Path(__file__)),'scenarios':len(channel_design.DOMAINS),'channel_pairs':len({r['pair_id'] for r in cases}),
            'isolation_conditions':len(cases),'operator_compatibility_cases':sum(len(r['attachments_checked']) for r in cases),
            'hosted_model_calls':0,'cases':cases,'checked':'Compared each actor’s complete initial messages, tools, ordinary workspace bytes and case data, the visibility graph, registered channel and exact cache responses including provenance. Only the separate allocation record and operator policy reflect the attached profile.',
            'scope':'Compatibility on the frozen Phase 1 source. Live pressure exposure, activation and kernel enforcement are separate evidence.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=audit(args.source.resolve());body=json.dumps(result,indent=2)+'\n'
    if args.output:
        with args.output.open('x') as f:f.write(body)
    else: print(body,end='')
