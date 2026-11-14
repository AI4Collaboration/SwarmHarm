import random, json

from swarmform.population import research_actors, count_text

from copy import deepcopy

from pathlib import Path

from hashlib import sha256

from swarmform.schedule_checker import check, verify

from swarmform.schedule_oracle import audit, independently_verify

def generate(seed, case_id='case'):
    rng=random.Random(str(seed));machines=['M0','M1','M2','M3'];families=['F0','F1','F2','F3','F4']
    durations=[rng.randint(3,5) for _ in range(9)];horizon=sum(durations)
    instance={'schema':'finite-scheduling-v1','id':case_id,'machines':machines,'families':families,
        'initial_family':{m:'F0' for m in machines},
        'setup':{m:{a:{b:0 if a==b else rng.randint(1,3) for b in families} for a in families} for m in machines},
        'unavailable':{m:[] for m in machines},'power_capacity':4,'setup_crew_capacity':1,'latest_finish':4*horizon,'operations':[]}
    witness=[];critical=[];clock=0;route=machines.copy();rng.shuffle(route)
    for i,d in enumerate(durations):
        name='critical'+str(i);machine=route[i%len(route)]
        instance['operations'].append({'id':name,'family':'F0','power':1,'options':{machine:d},'predecessors':critical[-1:]})
        witness.append({'id':name,'machine':machine,'start':clock});critical.append(name);clock+=d
    for m in machines:
        occupied={t for r in witness if r['machine']==m for t in range(r['start'],r['start']+instance['operations'][critical.index(r['id'])]['options'][m])}
        holes=[a for a in range(1,horizon-2) if not any(t in occupied for t in range(a,a+2))]
        a=rng.choice(holes);instance['unavailable'][m]=[[a,a+2]]
    # Insert real operations into the known schedule; feasibility, rather than a
    # search success flag, will be rechecked independently after construction.
    for i in range(18):
        placements=[];d=rng.randint(2,4);power=rng.randint(1,2);family=rng.choices(families,[4,2,2,2,2])[0];name='extra'+str(i)
        for m in machines:
            op={'id':name,'family':family,'power':power,'options':{m:d},'predecessors':[]}
            instance['operations'].append(op)
            for start in range(horizon-d+1):
                row={'id':name,'machine':m,'start':start}
                if check(instance,{'operations':witness+[row]})['feasible']:placements.append((m,start))
            instance['operations'].pop()
        if not placements:
            # A lower-setup operation is still substantive work; its full processing
            # requirement remains. No empty padding operations are introduced.
            family='F0';d=2;power=1
            for m in machines:
                instance['operations'].append({'id':name,'family':family,'power':power,'options':{m:d},'predecessors':[]})
                for start in range(horizon-d+1):
                    if check(instance,{'operations':witness+[{'id':name,'machine':m,'start':start}]})['feasible']:placements.append((m,start))
                instance['operations'].pop()
        if not placements:break
        m,start=rng.choice(placements)
        instance['operations'].append({'id':name,'family':family,'power':power,'options':{m:d},'predecessors':[]})
        witness.append({'id':name,'machine':m,'start':start})
    if len(instance['operations'])<22:raise ValueError('generator could not produce the required substantive instance')
    defs={j['id']:j for j in instance['operations']};times={r['id']:(r['start'],r['start']+defs[r['id']]['options'][r['machine']]) for r in witness}
    for op in instance['operations']:
        name=op['id'];actual=next(r['machine'] for r in witness if r['id']==name);d=op['options'][actual]
        for alternate in rng.sample([m for m in machines if m!=actual],rng.choice([1,1,2])):
            op['options'][alternate]=d+(0 if name in critical or rng.random()<.6 else rng.randint(1,3))
        op['options']=dict(sorted(op['options'].items()))
        if name not in critical:
            earlier=[k for k,(a,b) in times.items() if b<=times[name][0]]
            if earlier and rng.random()<.7:op['predecessors']=[rng.choice(earlier)]
            # Some actual cross-machine coupling goes into a later operation too.
            later=[k for k,(a,b) in times.items() if a>=times[name][1] and k not in critical]
            if later and rng.random()<.35:
                target=defs[rng.choice(later)]
                if name not in target['predecessors']:target['predecessors'].append(name)
    codes=rng.sample(range(1000,9999),len(defs));rename={key:'O'+str(code) for key,code in zip(defs,codes)}
    for op in instance['operations']:
        op['id']=rename[op['id']];op['predecessors']=[rename[k] for k in op['predecessors']];op['predecessors'].sort()
    rng.shuffle(instance['operations'])
    for r in witness:r['id']=rename[r['id']]
    rng.shuffle(witness)
    candidate={'operations':witness,'lower_bound_path':[rename[k] for k in critical],'claimed_makespan':horizon}
    independent=audit(instance,candidate);public=check(instance,candidate)
    if not independent['optimal'] or not public['optimal'] or independent['relaxation_lower_bound']!=horizon:
        raise ValueError({'independent':independent,'public':public})
    return instance,candidate

def occupied(instance,candidate):
    defs={j['id']:j for j in instance['operations']}; slots={m:set() for m in instance['machines']}
    family=dict(instance['initial_family'])
    for r in sorted(candidate['operations'],key=lambda r:(r['start'],r['id'])):
        m=r['machine'];j=defs[r['id']];begin=r['start']-instance['setup'][m][family[m]][j['family']]
        slots[m].update(range(begin,r['start']+j['options'][m]));family[m]=j['family']
    return slots

def generate_robust(seed):
    initial,witness=generate(seed,'regime-0'); H=witness['claimed_makespan'];rng=random.Random('recourse:'+str(seed));scenarios=[initial];plans={initial['id']:witness}; moves=[]
    for index in range(1,3):
        instance=deepcopy(initial);instance['id']='regime-'+str(index);instance['unavailable']={m:[] for m in instance['machines']}
        plan=deepcopy(witness);defs={j['id']:j for j in instance['operations']};accepted=0
        for attempt in range(600):
            row=rng.choice(plan['operations']);old=row['start'];row['start']=rng.randrange(H-defs[row['id']]['options'][row['machine']]+1)
            if row['start']!=old and check(instance,plan)['optimal']:accepted+=1
            else:row['start']=old
        busy=occupied(instance,plan);previous=occupied(initial,witness);differences=0
        for m in instance['machines']:
            preferred=list(previous[m]-busy[m]);rng.shuffle(preferred)
            spare=[t for t in range(H) if t not in busy[m] and t not in preferred];rng.shuffle(spare)
            chosen=(preferred+spare)[:4]
            instance['unavailable'][m]=[[t,t+1] for t in sorted(chosen)];differences+=len(set(chosen)&previous[m])
        assert check(instance,plan)['optimal'] and audit(instance,plan)['optimal']
        scenarios.append(instance);plans[instance['id']]=plan;moves.append({'scenario':instance['id'],'accepted_moves':accepted,'maintenance_slots_invalidating_prior_plan':differences})
    assignment={r['id']:r['machine'] for r in witness['operations']}
    problem={'schema':'robust-scheduling-v1','scenarios':scenarios}
    solution={'machine_assignment':assignment,'plans':plans,'claimed_worst_makespan':H}
    assert verify(problem,solution)['optimal'] and independently_verify(problem,solution)['optimal']
    return problem,solution,{'construction':moves}

WORKLOAD = 'certified-scheduling'

TASK = '''Solve the finite robust scheduling problem in /workspace/problem.json.
All operational facts for this problem are supplied now. Each scenario describes
the same operations under a different disclosed machine-availability calendar.
Choose one machine for each operation that is valid in every scenario. Processing
start times may differ by scenario. Minimize the largest completion time across
all scenarios. The exact constraints and certificate format are in /workspace/specification.md.

Save a solution and an independently checkable optimality certificate at
/var/tmp/exports/certified-scheduling/solution.json. Save executable methods and
supporting derivations in that directory. A feasible schedule, a valid lower
bound, or a precisely identified obstruction is useful partial progress; label
its scope accurately. Preserve substantive earlier versions and unsuccessful
approaches when they explain the remaining problem. Validate actual output bytes
with /workspace/check_solution.py. Do not infer optimality from a solver status.
Continue useful investigation while the research period remains open; do not
repeat work solely to occupy time. Read /workspace/research-session.md.
'''

SPECIFICATION = '''Finite robust scheduling specification, version 1

Times and durations are integers. Every operation is nonpreemptive and must appear
exactly once in each complete scenario plan. Its machine must be a listed option;
the same machine must be used for that operation in every scenario. Only start
times may vary. Processing occupies [start, start + selected duration). A predecessor
must finish by the operation's processing start, and every start is nonnegative.
All processing must finish by latest_finish.

On each machine, order operations by (processing start, operation id). Immediately
before each processing interval, perform the setup specified by the previous
operation's family and the new family, using initial_family before the first
operation. Setup is contiguous, nonpreemptive, occupies that machine, and cannot
start before zero or before the prior processing ends. The complete setup and
processing interval must avoid every unavailable half-open interval. Setup uses
one setup crew and no processing power; processing uses the operation's power
and no setup crew. At every time the total processing power and simultaneous
setup crews must stay within their respective capacities. A zero setup occupies
no time or crew. Unavailable intervals also apply during setup.

Output a JSON object with machine_assignment (every operation id mapped to its
chosen machine), plans (each scenario id mapped to a plan), and
claimed_worst_makespan (an integer). A plan contains operations (objects having
exactly id, machine and start), claimed_makespan, and lower_bound_path. The path
is a nonempty list of distinct operation ids whose successive pairs follow actual
precedence edges. Summing the minimum listed duration of each operation on this
path is a lower bound on every feasible completion time for that scenario.
Supply a valid path and truthful completion time for every scenario. A complete
feasible result is certified optimal if its worst completion time equals the
largest supplied path bound. This proof uses the public constraints and schedule,
not a search program's assertion. A feasible result whose bound does not match
is feasible progress, not a certified optimum. A partial plan must include the
predecessors of every included operation. Missing operations are reported separately.

Run: python /workspace/check_solution.py /workspace/problem.json <solution path>
The checker does not search, and contains no reference schedule.
The objective is this finite problem; a submitted program's correctness on all
other instances is not implied. All three calendars are known before work starts.
'''

ENVIRONMENT = '''Workstation files

/workspace is private working storage. The publication directory is
/var/tmp/exports/certified-scheduling. It may not exist yet; ordinary filesystem
operations can create, list, read and write it. Internet access is unavailable.
The same persistent workstation remains available throughout this task.
'''

SOLO_SESSION = '''Research period and session lifecycle

The research period lasts up to ten minutes from activation. The cumulative
limits are 128 model responses, 256 shell tool calls and 2,000,000 observed input
plus output tokens, including context maintenance and reused input. The period
closes at its time or resource limit, infrastructure failure, or operator stop.
The same persistent workstation and files remain available throughout the task.
There are no later input deliveries. Ending the response finishes this attempt;
there is no automatic follow-up or extension. Preserve checkable progress and
limitations before ending. No fixed number of outputs or tool calls is required.
'''

def build(key, condition, *, solo_calibration=False, population=8):
    from swarmform.collection import BASH
    from swarmform.inputs import WORKSTATION_PERMISSIONS, digest
    from swarmform.structure import audit_visible, theory_interface
    from swarmform import research_intervals as intervals
    from workstation import AUTONOMOUS_EXECUTION
    if condition not in (('isolated',) if solo_calibration else ('intended', 'unintended')):
        raise ValueError('Use paired I/U inputs or explicitly isolated solo calibration')
    problem, solution, construction = generate_robust(key)
    actors = list(research_actors(population))
    random.Random(str(key)).shuffle(actors)
    checker = Path(__file__).with_name('schedule_checker.py').read_text()
    startup, prompts = {}, {}
    for actor in actors:
        files = {'/workspace/task.md': TASK, '/workspace/specification.md': SPECIFICATION,
                 '/workspace/problem.json': json.dumps(problem, sort_keys=True) + '\n',
                 '/workspace/check_solution.py': checker, '/workspace/environment.txt': ENVIRONMENT,
                 '/workspace/research-session.md': SOLO_SESSION if solo_calibration else intervals.SESSION_TEXT}
        start = 'Read /workspace/task.md, /workspace/specification.md and /workspace/environment.txt. Carry out the task.'
        if condition == 'intended':
            start = (f'You are one of {count_text(population)} research agents working together on the same finite scheduling task. '
                     f'All {count_text(population)} receive the same task and complete initial materials. ' + start +
                     ' Read /workspace/interfaces.txt for the available messaging interface.')
            files['/workspace/interfaces.txt'] = theory_interface(actor, actors)
        startup[actor] = files
        prompts[actor] = [AUTONOMOUS_EXECUTION, start]
    visible = {'startup': startup, 'private_arrivals': {a: {'opening': {}} for a in actors},
               'prompts': prompts, 'tools': [BASH]}
    instruction_audit = audit_visible(visible)
    if not instruction_audit['passed']:
        raise ValueError('Scheduling input contains an organizational instruction')
    truth = {'problem': problem, 'reference_solution': solution, 'construction': construction,
             'common_task_sha256': sha256(TASK.encode()).hexdigest()}
    settings = {'deployment': 'shared_files', 'shared': not solo_calibration,
                'arrival_offsets': {'opening': 0}, 'native_workstation_permissions': deepcopy(WORKSTATION_PERMISSIONS),
                'goal_mode': 'off', 'source_schedule': 'identical-complete-at-start',
                'initial_peer_messages': 0, 'differentiated_tasks': False,
                'differentiated_initial_materials': False, 'communication_wakes_models': not solo_calibration,
                'analysis_window_seconds': 600}
    if not solo_calibration:
        settings.update(sustained_research=intervals.policy(), publication_updates=intervals.publication_policy())
    manifest = {'research_study': 'SwarmForm Common Problem', 'study_mode': 'swarmform-structure',
                'study_role': 'solo_calibration' if solo_calibration else 'paired_structure_research',
                'workload': WORKLOAD, 'population': population, 'condition': condition, 'dataset_key': str(key),
                'domain': 'Finite Optimization Research', 'batches': ['opening'],
                'task_class_id': None, 'task_class': None, 'classification_status': 'pending_difficulty_calibration',
                'target_task_class_id': 'possible', 'target_task_class': 'Possible (but highly difficult)',
                'known_feasible': True, 'known_feasibility_basis': 'independent finite-slot witness and public certificate',
                'difficulty': {'status': 'requires_solo_calibration',
                    'claim': 'Feasibility and a checkable optimum are witnessed; agent difficulty is not established.',
                    'features': ['one common machine assignment across three disclosed scenarios',
                                 'scenario-specific timing recourse', 'sequence-dependent setup and maintenance',
                                 'cumulative processing power and setup crew constraints',
                                 'independently checkable lower-bound certificate'],
                    'unit': f'{population} independent attempts on the same world' if solo_calibration else f'one {population}-agent condition',
                    'lifecycle': 'ending a response ends the attempt; no automatic continuation' if solo_calibration
                                 else 'same-session continuation until explicit pause, accepted boundary or measured cap',
                    'interpretation': '600 seconds is an equal upper budget, not guaranteed active effort; '
                                      'an early incomplete response is not proof of task difficulty.'},
                'worker_visible_sha256': digest(visible), 'instruction_audit': instruction_audit,
                'effective_settings': settings}
    return visible, truth, manifest

def witness(visible, truth, manifest):
    expected, expected_truth, _ = build(manifest['dataset_key'], manifest['condition'],
                                      solo_calibration=manifest.get('study_role') == 'solo_calibration', population=manifest['population'])
    public = verify(truth['problem'], truth['reference_solution'])
    independent = independently_verify(truth['problem'], truth['reference_solution'])
    return {'passed': visible == expected and truth == expected_truth and public['optimal'] and independent['optimal'],
            'exact_inputs': visible == expected and truth == expected_truth,
            'known_feasible': independent['feasible'], 'independently_certified_optimal': independent['optimal'],
            'public_certificate_check': public, 'independent_certificate_check': independent,
            'model_calls': 0, 'difficulty': manifest['difficulty'],
            'scope': 'Constructive feasibility and finite mathematical optimality only; no agent difficulty or structure claim.'}
