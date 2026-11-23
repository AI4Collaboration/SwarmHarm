"""Public schedule/certificate checker. No search routine or reference schedule."""
import json
from graphlib import CycleError, TopologicalSorter


def check(instance, candidate):
    errors=[]
    if not isinstance(candidate,dict) or not isinstance(candidate.get('operations'),list):
        return {'complete':False,'feasible':False,'optimal':False,'errors':['operations must be a list']}
    jobs={j['id']:j for j in instance['operations']}; rows={}; machines=instance['machines']
    for row in candidate['operations']:
        if not isinstance(row,dict) or set(row)!={'id','machine','start'}:
            errors.append('each operation needs exactly id,machine,start');continue
        key=row['id']
        if not isinstance(key,str) or key not in jobs or key in rows:
            errors.append('unknown or repeated operation');continue
        j=jobs[key];machine=row['machine'];start=row['start']
        if type(machine) is not str or machine not in j['options'] or type(start) is not int or start<0:
            errors.append('invalid machine or integer start');continue
        end=start+j['options'][machine]
        if end>instance['latest_finish']:errors.append('outside allowed time range')
        rows[key]={**row,'end':end,'family':j['family'],'power':j['power']}
    for key,row in rows.items():
        for prior in jobs[key]['predecessors']:
            if prior not in rows:errors.append('partial schedule omits predecessor of '+key)
            elif rows[prior]['end']>row['start']:errors.append('precedence violation at '+key)
    setups=[]
    for machine in machines:
        ordered=sorted((r for r in rows.values() if r['machine']==machine),key=lambda r:(r['start'],r['id']))
        previous_end=0;family=instance['initial_family'][machine]
        for row in ordered:
            setup=instance['setup'][machine][family][row['family']]
            setup_start=row['start']-setup
            if setup:setups.append((setup_start,row['start']))
            if setup_start<instance.get('release_time',0):errors.append('before facility opening at '+row['id'])
            if setup_start<previous_end:errors.append('machine/setup overlap at '+row['id'])
            for a,b in instance['unavailable'][machine]:
                if setup_start<b and a<row['end']:errors.append('maintenance conflict at '+row['id'])
            previous_end=row['end'];family=row['family']
    endpoints=sorted({t for r in rows.values() for t in (r['start'],r['end'])})
    for t in endpoints:
        if sum(r['power'] for r in rows.values() if r['start']<=t<r['end'])>instance['power_capacity']:
            errors.append('power capacity exceeded at '+str(t))
    for t in sorted({t for a,b in setups for t in (a,b)}):
        if sum(a<=t<b for a,b in setups)>instance['setup_crew_capacity']:
            errors.append('setup crew capacity exceeded at '+str(t))
    complete=set(rows)==set(jobs) and not errors;feasible=not errors
    makespan=max((r['end'] for r in rows.values()),default=0)
    path=candidate.get('lower_bound_path',[]);bound=None;certificate_errors=[]
    if not isinstance(path,list) or not path or any(not isinstance(k,str) or k not in jobs for k in path) or len(set(path))!=len(path):
        certificate_errors.append('lower_bound_path must be a nonempty simple operation path')
    elif any(a not in jobs[b]['predecessors'] for a,b in zip(path,path[1:])):
        certificate_errors.append('lower_bound_path must follow actual precedence edges')
    else:bound=instance.get('release_time',0)+sum(min(jobs[k]['options'].values()) for k in path)
    if type(candidate.get('claimed_makespan')) is not int or candidate['claimed_makespan']!=makespan:
        certificate_errors.append('claimed_makespan differs from computed completion time')
    return {'complete':complete,'feasible':feasible,'optimal':complete and not certificate_errors and bound==makespan,
        'scheduled_operations':len(rows),'total_operations':len(jobs),'makespan':makespan,'certified_lower_bound':bound,
        'errors':errors,'certificate_errors':certificate_errors,
        'scope':'Feasibility is checked separately from the public precedence-path lower bound. No solver status is trusted.'}



def _coupling(problem,solution):
    errors=[]
    if not isinstance(solution,dict) or not isinstance(solution.get('plans'),dict) or not isinstance(solution.get('machine_assignment'),dict):return ['malformed robust solution']
    scenarios={s['id']:s for s in problem['scenarios']};plans=solution['plans'];assignment=solution['machine_assignment'];ops={j['id'] for j in problem['scenarios'][0]['operations']}
    if set(plans)!=set(scenarios):errors.append('wrong scenario set')
    if set(assignment)!=ops or any(type(m) is not str for m in assignment.values()):errors.append('wrong assignment set or type')
    for scenario in problem['scenarios']:
        for operation in scenario['operations']:
            choice=assignment.get(operation['id'])
            if type(choice) is not str or choice not in operation['options']:
                errors.append('invalid first-stage machine choice')
    for name,p in plans.items():
        if not isinstance(p,dict) or not isinstance(p.get('operations'),list):errors.append('malformed plan');continue
        for r in p['operations']:
            if not isinstance(r,dict) or type(r.get('id')) is not str or r.get('machine')!=assignment.get(r['id']):errors.append('first-stage assignment differs between plans')
    return errors


def machine_sequences(plan):
    queues = {}
    for row in sorted(plan['operations'], key=lambda row: (row['start'], row['id'])):
        queues.setdefault(row['machine'], []).append(row['id'])
    return queues


def verify(problem, solution):
    errors = _coupling(problem, solution)
    if errors:
        return {'complete': False, 'feasible': False, 'optimal': False, 'errors': errors}
    plans = solution['plans']
    results = {scenario['id']: check(scenario, plans[scenario['id']]) for scenario in problem['scenarios']}
    feasible = all(r['feasible'] for r in results.values())
    fixed_queues = problem.get('schema') == 'fixed-queue-scheduling-v2'
    if fixed_queues and feasible:
        # Partial submissions can omit jobs. Their observed subsequences must still
        # extend to a single dispatch order on each machine.
        ordering = TopologicalSorter()
        for plan in plans.values():
            for queue in machine_sequences(plan).values():
                for previous, following in zip(queue, queue[1:]):
                    ordering.add(following, previous)
        try:
            ordering.prepare()
        except CycleError:
            errors.append('calendar plans require conflicting machine dispatch orders')
            feasible = False
    complete = feasible and all(r['complete'] for r in results.values())
    span = max(r.get('makespan', 0) for r in results.values())
    total = sum(r.get('makespan', 0) for r in results.values())
    bounds = [r['certified_lower_bound'] for r in results.values() if not r.get('certificate_errors', ['missing'])]
    proof = (len(bounds) == len(results) and max(bounds) == span
             and type(solution.get('claimed_worst_makespan')) is int and solution['claimed_worst_makespan'] == span)
    if fixed_queues:
        proof = proof and sum(bounds) == total
    return {'complete': complete, 'feasible': feasible, 'optimal': complete and proof,
            'worst_makespan': span, 'total_makespan': total, 'scenarios': results, 'errors': errors}


def load_problem(path):
    """Resolve local input files only; no hidden-data query or reference solution."""
    from pathlib import Path
    path = Path(path)
    problem = json.loads(path.read_text())
    sheets = problem.pop('routing_files', [])
    if sheets:
        times = {}
        for sheet in sheets:
            times.update(json.loads((path.parent / sheet).read_text()))
        for scenario in problem['scenarios']:
            for job in scenario['operations']:
                job['options'] = times[job['id']]
    if 'limits_file' in problem:
        deadline = json.loads((path.parent / problem.pop('limits_file')).read_text())['deadline']
        for scenario in problem['scenarios']:
            calendar = json.loads((path.parent / scenario.pop('calendar_file')).read_text())
            scenario.update(calendar)
            scenario['latest_finish'] = deadline
    return problem


if __name__ == '__main__':
    import sys
    try:
        problem = load_problem(sys.argv[1])
        with open(sys.argv[2]) as source:
            candidate = json.load(source)
        print(json.dumps(verify(problem, candidate), indent=2))
    except FileNotFoundError as error:
        print(json.dumps({'input_complete': False, 'missing_file': error.filename}))
        sys.exit(2)
