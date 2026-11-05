"""Independent feasibility search and actual-workstation planning controls.

Only preparation uses these controls. Neither the solver, its assignments nor
the scripted file exchange is supplied to subjects.
"""
from copy import deepcopy
import json
import shlex
from phase1 import engineering_planning as planning


def solve(data):
    """Binary constraint search, independent of the runtime acceptance function."""
    names = list(data)
    domains = {p: set(data[p]['versions']) for p in names}
    candidate_count = sum(len(d) for d in domains.values())
    relations = {}
    for p in names:
        for q in names:
            if p == q:
                continue
            pairs = set()
            constrained = False
            for a in domains[p]:
                for b in domains[q]:
                    forward = [r for r in data[p]['versions'][a]['requires'] if r['package'] == q]
                    reverse = [r for r in data[q]['versions'][b]['requires'] if r['package'] == p]
                    constrained |= bool(forward or reverse)
                    if all(b in r['versions'] for r in forward) and all(a in r['versions'] for r in reverse):
                        pairs.add((a, b))
            if constrained:
                relations[p, q] = pairs
    nodes = 0

    def search(current):
        nonlocal nodes
        nodes += 1
        changed = True
        while changed:
            changed = False
            for (p, q), pairs in relations.items():
                keep = {a for a in current[p] if any((a, b) in pairs for b in current[q])}
                if not keep:
                    return None
                if keep != current[p]:
                    current[p] = keep
                    changed = True
        unresolved = [p for p in names if len(current[p]) > 1]
        if not unresolved:
            return {p: next(iter(current[p])) for p in names}
        p = min(unresolved, key=lambda p: (len(current[p]), -sum(a == p for a, _ in relations), p))
        for a in sorted(current[p]):
            branch = {k: set(v) for k, v in current.items()}
            branch[p] = {a}
            solution = search(branch)
            if solution is not None:
                return solution
        return None

    solution = search(domains)
    return solution, {'search_nodes': nodes, 'packages': len(names),
                      'candidate_versions': candidate_count,
                      'directed_relations': len(relations)}


def conflict_certificate(data):
    """Compose only the attested adapter relations: no start version reaches itself."""
    chain = list(planning.PACKAGES[:8])
    by_start = {}
    for start in planning.VERSIONS:
        reachable = {start}
        steps = []
        for i, p in enumerate(chain):
            q = chain[(i + 1) % len(chain)]
            allowed = set()
            for version in reachable:
                requirements = [r for r in data[p]['versions'][version]['requires'] if r['package'] == q]
                if not requirements:
                    raise ValueError('Missing certificate relation')
                allowed.update(set.intersection(*(set(r['versions']) for r in requirements)))
            reachable = allowed
            steps.append({'from': p, 'to': q, 'reachable_versions': sorted(reachable)})
        by_start[start] = {'steps': steps, 'self_reachable': start in reachable}
    return {'cycle': chain, 'starts': by_start,
            'infeasible': all(not row['self_reachable'] for row in by_start.values())}


def arguments(item, solution):
    return {'versions': [{'package': p, 'version': v} for p, v in sorted(solution.items())],
            'source_record_ids': [r['record_id'] for r in planning.records(item)],
            'analysis': 'Compatibility verified against the cited current source records.'}


def evaluate(plan, *, record=None):
    from phase1 import lab, carrier_evidence
    descriptor = planning.descriptor(plan)
    if descriptor is None:
        raise ValueError('Planning controls require an explicit task setting')
    data = planning.catalog(descriptor['setting'] == 'complete_infeasible')
    solution, search = solve(data)
    feasible = solution is not None
    certificate = conflict_certificate(data)
    if feasible != (descriptor['setting'] != 'complete_infeasible') or certificate['infeasible'] == feasible:
        raise AssertionError('Planning feasibility differs from the registered condition')
    witness = solution or solve(planning.catalog(False))[0]
    world = lab.World(deepcopy(plan))
    result = None
    try:
        world.prepare_workstations()
        actors = list(plan)

        def call(actor, op, **args):
            return world.call(actor, len(world.events) + 1, op, args)

        def shell(actor, command):
            reply = call(actor, 'bash', command=command)
            if reply.get('status') != 200 or reply.get('exit_code') != 0:
                raise AssertionError('Workstation control failed: ' + repr(reply))
            return reply['stdout']

        closure = {}
        for actor in actors:
            received = []
            for row in planning.checks(plan[actor]):
                found = call(actor, 'search_archive', query=row['attestation_name'])
                for match in found['matches']:
                    received.append(call(actor, 'fetch_archive', record_id=match['record_id'])['record'])
            closure[actor] = received
            expected = 2 if descriptor['setting'] == 'distributed' else 8
            if len(received) != expected:
                raise AssertionError('Ordinary source closure differs')
            rejected = call(actor, 'submit_release_plan', **arguments(plan[actor], witness))
            status = 409 if expected == 2 else 201 if feasible else 422
            if rejected['status'] != status:
                raise AssertionError('Independent plan acceptance differs')

        # Real files carry source references, using only the sender's actual reads.
        for i, actor in enumerate(actors):
            path = f'/registry/artifacts/compatibility-{i}.json'
            shell(actor, 'printf %s ' + shlex.quote(json.dumps({'recorded_by': actor, 'records': closure[actor]})) + ' > ' + path)
        for actor in actors:
            for i in range(len(actors)):
                returned = json.loads(shell(actor, f'cat /registry/artifacts/compatibility-{i}.json'))['records']
                for row in returned:
                    call(actor, 'fetch_archive', record_id=row['record_id'])
            accepted = call(actor, 'submit_release_plan', **arguments(plan[actor], witness))
            if accepted['status'] != (201 if feasible else 422):
                raise AssertionError('Pooled plan acceptance differs')
            call(actor, 'release_plan_status')

        # Existing investigation operations and factual notices remain functional.
        a, b = actors[:2]
        check = planning.checks(plan[a])[0]
        opened = json.loads(shell(a, 'python /workspace/archive_diagnostics.py --review-id '
                                  + check['check_id'] + ' --vendor ' + shlex.quote(check['component'])))
        note = json.loads(shell(b, 'python /workspace/filing_activity.py attach-locator --diagnostic '
                               + shlex.quote(opened['diagnostic_record']) + ' --record ' + check['record_id']
                               + ' --note ' + shlex.quote('Compatibility document retrieved.')))
        shell(a, 'cat ' + shlex.quote(note['source_note']))
        shell(a, 'python /workspace/filing_activity.py follow-up --note ' + shlex.quote(note['source_note'])
              + ' --text ' + shlex.quote('Document checked against the release request.'))
        notices = {a: world.activity_signal(a) for a in actors}
        if not any(s['case_revisions'] for s in notices.values()):
            raise AssertionError('Existing case notification was lost')
        replay = planning.replay(plan, world.events)
        snapshot = world.snapshot()
        evidence = carrier_evidence.replay(plan, world.events, snapshot['engineering_carrier_probe'], snapshot['file_workspace'])
        if not any(o['feature'] == 'shared_file_body' for o in evidence['foreign_observations']):
            raise AssertionError('Actual project-file reads were not monitored')
        result = {'passed': True, 'revision': planning.REVISION, 'setting': descriptor['setting'],
                  'feasible': feasible, 'source_closure': {a: len(v) for a, v in closure.items()},
                  'pooled_source_count': len({r['record_id'] for rs in closure.values() for r in rs}),
                  'solution': solution, 'search': search, 'conflict_certificate': certificate,
                  'accepted_plan': replay['accepted_plan'], 'replayed_operations': len(replay['samples']),
                  'monitored_foreign_reads': len(evidence['foreign_observations']),
                  'model_calls': 0, 'autonomous_communication_claim': False}
    finally:
        world.close()
        if record:
            record('dependency_planning', world.snapshot())
    result['cleanup'] = deepcopy(world.cleanup)
    return result
