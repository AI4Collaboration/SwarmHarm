"""Operator-only independent finite-slot feasibility and DAG bound proof.

Does not import the public checker, run a participant solver, or trust a search flag.
"""

def audit(instance, candidate):
    reasons=[]; ops=instance['operations']; n=len(ops); definitions={x['id']:x for x in ops}; selected={}
    if not isinstance(candidate,dict) or not isinstance(candidate.get('operations'),list):return {'feasible':False,'complete':False,'optimal':False,'reasons':['malformed output']}
    for row in candidate['operations']:
        if not isinstance(row,dict) or set(row)!=set(('id','machine','start')):reasons.append('shape');continue
        name=row['id']
        if type(name) is not str or name not in definitions or name in selected:reasons.append('identity');continue
        d=definitions[name]; m=row['machine']; t=row['start']
        if type(m) is not str or m not in d['options'] or type(t) is not int or t<0:reasons.append('choice');continue
        stop=t+d['options'][m]
        if stop > instance['latest_finish']:
            reasons.append('range')
        selected[name]=(m,t,stop)
    used={m:{} for m in instance['machines']}; watts={};crews={}; last={m:instance['initial_family'][m] for m in used}
    # Build machine event sequences independently, then mark each occupied integer slot.
    for name,(m,start,stop) in sorted(selected.items(),key=lambda x:(x[1][1],x[0])):
        d=definitions[name]; change=instance['setup'][m][last[m]][d['family']];begin=start-change
        if begin<instance.get('release_time',0):reasons.append('before opening')
        for tick in range(begin,stop):
            if tick in used[m]:reasons.append('occupied machine')
            used[m][tick]=name
            if any(lo<=tick<hi for lo,hi in instance['unavailable'][m]):reasons.append('unavailable')
        for tick in range(begin,start):crews[tick]=crews.get(tick,0)+1
        for tick in range(start,stop):watts[tick]=watts.get(tick,0)+d['power']
        last[m]=d['family']
        for parent in d['predecessors']:
            if parent not in selected or selected[parent][2]>start:reasons.append('predecessor')
    if any(x>instance['setup_crew_capacity'] for x in crews.values()):reasons.append('setup crew')
    if any(x>instance['power_capacity'] for x in watts.values()):reasons.append('power')
    # Independently compute an earliest-completion relaxation. Every legal assignment
    # has duration >= its fastest option, and each actual precedence edge is mandatory.
    pending=set(definitions); distances={}; paths={}
    while pending:
        ready=[k for k in pending if all(p in distances for p in definitions[k]['predecessors'])]
        if not ready:raise ValueError('invalid cyclic instance')
        for k in ready:
            parents=definitions[k]['predecessors'];p=max(parents,key=lambda p:distances[p]) if parents else None
            distances[k]=(distances[p] if p else 0)+min(definitions[k]['options'].values());paths[k]=(paths[p] if p else [])+[k];pending.remove(k)
    endpoint=max(distances,key=distances.get);lower=instance.get('release_time',0)+distances[endpoint];span=max((r[2] for r in selected.values()),default=0)
    complete=len(selected)==n and not reasons
    # Check the participant's own certificate too; oracle knowledge alone is not an output certificate.
    path=candidate.get('lower_bound_path');proof=False;provided=None
    if isinstance(path,list) and path and all(type(k) is str and k in definitions for k in path) and len(path)==len(set(path)):
        if all(a in definitions[b]['predecessors'] for a,b in zip(path,path[1:])):
            provided=instance.get('release_time',0)+sum(min(definitions[k]['options'].values()) for k in path)
            proof=provided==span and type(candidate.get('claimed_makespan')) is int and candidate['claimed_makespan']==span
    return {'feasible':not reasons,'complete':complete,'optimal':complete and proof,'makespan':span,
        'relaxation_lower_bound':lower,'independent_bound_path':paths[endpoint],'provided_lower_bound':provided,
        'scheduled_operations':len(selected),'total_operations':n,'reasons':sorted(set(reasons)),
        'proof_method':'finite integer-slot occupancy plus independent acyclic precedence relaxation; no search success flag'}

def independently_verify(problem,solution):
    if type(solution) is not dict:return {'optimal':False,'feasible':False}
    choices=solution.get('machine_assignment');plans=solution.get('plans')
    if type(choices) is not dict or type(plans) is not dict:return {'optimal':False,'feasible':False}
    expected_ids=[j['id'] for j in problem['scenarios'][0]['operations']]
    if set(choices)!=set(expected_ids) or set(plans)!={s['id'] for s in problem['scenarios']}:return {'optimal':False,'feasible':False}
    for instance in problem['scenarios']:
        for operation in instance['operations']:
            machine=choices[operation['id']]
            if type(machine) is not str or machine not in operation['options']:
                return {'optimal':False,'feasible':False,'complete':False,'reasons':['invalid common machine decision']}
    results=[];consistent=True
    for instance in problem['scenarios']:
        p=plans[instance['id']]
        if not isinstance(p,dict) or not isinstance(p.get('operations'),list):return {'feasible':False,'complete':False,'optimal':False}
        a=audit(instance,p);results.append(a)
        for name in expected_ids:
            observed=[r.get('machine') for r in p['operations'] if isinstance(r,dict) and r.get('id')==name]
            if len(observed)>1 or (observed and observed[0]!=choices[name]):consistent=False
    feasible=consistent and all(a['feasible'] for a in results);complete=feasible and all(a['complete'] for a in results);span=max(a.get('makespan',0) for a in results);lower=max(a.get('provided_lower_bound') or 0 for a in results)
    ownclaims=all(type(plans[s['id']].get('claimed_makespan')) is int and plans[s['id']]['claimed_makespan']==a.get('makespan') for s,a in zip(problem['scenarios'],results))
    fixed_queues = problem.get('schema') == 'fixed-queue-scheduling-v2'
    if fixed_queues and feasible:
        # Independently merge observed prefixes by taking a job only when it is
        # at the front of every calendar sequence in which it still appears.
        for machine in problem['scenarios'][0]['machines']:
            sequences = [[r['id'] for r in sorted(plan['operations'], key=lambda r: (r['start'], r['id']))
                          if r['machine'] == machine] for plan in plans.values()]
            while any(sequences):
                blocked = {job for sequence in sequences for job in sequence[1:]}
                ready = {sequence[0] for sequence in sequences if sequence} - blocked
                if not ready:
                    feasible = complete = False
                    break
                for sequence in sequences:
                    if sequence and sequence[0] in ready:
                        sequence.pop(0)
    total = sum(a.get('makespan', 0) for a in results)
    proof = (ownclaims and all(a.get('provided_lower_bound') is not None for a in results)
             and lower == span and type(solution.get('claimed_worst_makespan')) is int
             and solution['claimed_worst_makespan'] == span)
    if fixed_queues:
        proof = proof and all(a['provided_lower_bound'] == a['makespan'] for a in results)
    return {'feasible': feasible, 'complete': complete, 'optimal': complete and proof,
            'worst_makespan': span, 'total_makespan': total,
            'independent_lower_bound': max(a.get('relaxation_lower_bound', 0) for a in results),
            'scenarios': results}
